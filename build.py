#!/usr/bin/env python3
"""Simple Python replacement for the Makefile targets.

Usage examples:
    ./build.py compile
    ./build.py simulate
    ./build.py waveform
    ./build.py clean
    ./build.py install --dir ../other_project
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Literal, TypedDict, cast


class InstallConfig(TypedDict):
    """Schema for install.config.json."""
    frameworkFiles: list[str]

    @staticmethod
    def validateInstallConfig(rawConfig: object) -> "InstallConfig":
        """Validate and return install config with runtime type checks."""
        if not isinstance(rawConfig, dict):
            raise ValueError("install.config.json must contain a JSON object")

        frameworkFiles = rawConfig.get("frameworkFiles")
        if not isinstance(frameworkFiles, list) or not all(isinstance(item, str) for item in frameworkFiles):
            raise ValueError("install.config.json key 'frameworkFiles' must be a list[str]")

        return {
            "frameworkFiles": frameworkFiles,
        }


class BuildConfig(TypedDict):
    """Schema for build.config.json."""
    sourceDirectory: str
    verilogSuffixes: list[str]
    testbenchSuffixes: list[str]
    includeSuffixes: list[str]

    @staticmethod
    def validateBuildConfig(rawConfig: object) -> "BuildConfig":
        """Validate and return build config with runtime type checks."""
        if not isinstance(rawConfig, dict):
            raise ValueError("build.config.json must contain a JSON object")

        sourceDirectory = rawConfig.get("sourceDirectory")
        verilogSuffixes = rawConfig.get("verilogSuffixes")
        testbenchSuffixes = rawConfig.get("testbenchSuffixes")
        includeSuffixes = rawConfig.get("includeSuffixes")

        if not isinstance(sourceDirectory, str):
            raise ValueError("build.config.json key 'sourceDirectory' must be a string")
        if not isinstance(verilogSuffixes, list) or not all(isinstance(item, str) for item in verilogSuffixes):
            raise ValueError("build.config.json key 'verilogSuffixes' must be a list[str]")
        if not isinstance(testbenchSuffixes, list) or not all(isinstance(item, str) for item in testbenchSuffixes):
            raise ValueError("build.config.json key 'testbenchSuffixes' must be a list[str]")
        if not isinstance(includeSuffixes, list) or not all(isinstance(item, str) for item in includeSuffixes):
            raise ValueError("build.config.json key 'includeSuffixes' must be a list[str]")

        return {
            "sourceDirectory": sourceDirectory,
            "verilogSuffixes": verilogSuffixes,
            "testbenchSuffixes": testbenchSuffixes,
            "includeSuffixes": includeSuffixes,
        }


class IncludeConfig(TypedDict):
    """Schema for <testbench>.include config files."""
    include: list[str]

    @staticmethod
    def validateIncludeConfig(rawConfig: object) -> "IncludeConfig":
        """Validate and return include config with runtime type checks."""
        if not isinstance(rawConfig, dict):
            raise ValueError("include config must contain a JSON object")

        includeEntries = rawConfig.get("include")
        if not isinstance(includeEntries, list) or not all(isinstance(item, str) for item in includeEntries):
            raise ValueError("include config key 'include' must be a list[str]")

        return {
            "include": includeEntries,
        }


TargetName = Literal["compile", "simulate", "waveform", "watch", "clean", "install", "uninstall"]


def getBuildConfig() -> BuildConfig:
    with open('build.config.json', 'r') as f:
        rawConfig: object = json.load(f)
    try:
        return BuildConfig.validateBuildConfig(rawConfig)
    except ValueError as error:
        print(f"invalid build config: {error}")
        sys.exit(1)


def getSourceDirectory() -> pathlib.Path:
    return pathlib.Path(getBuildConfig()['sourceDirectory'])


def getTestbenchSuffixes() -> list[str]:
    return getBuildConfig().get('testbenchSuffixes', ['_tb', '.test'])


def getIncludeSuffixes() -> list[str]:
    return getBuildConfig().get('includeSuffixes', ['.include.json'])


def getVerilogSuffixes() -> list[str]:
    return getBuildConfig().get('verilogSuffixes', ['.sv', '.v'])


def getSources() -> list[pathlib.Path]:
    """Return all source files in the source directory with the specified verilog suffixes."""
    sourceDirectory = getSourceDirectory()
    # rglob returns generators; concatenate by converting each to a list first
    sources = []
    for suffix in getVerilogSuffixes():
        sources += list(sourceDirectory.rglob(f"*{suffix}"))
    return sources


def getTestbenches(patterns: list[str] | None = None) -> list[pathlib.Path]:
    """Return all testbench files in the source directory matching the specified testbench identification patterns."""
    if patterns is None:
        patterns = getTestbenchSuffixes()
    testBenches: list[pathlib.Path] = []
    for sourcePath in getSources():
        if any(pat in sourcePath.name for pat in patterns):
            testBenches.append(sourcePath)
    return testBenches


def findIncludeConfigFile(testBench: pathlib.Path) -> pathlib.Path | None:
    """Return the existing include config path for a testbench, if present."""
    for suffix in getIncludeSuffixes():
        candidate = testBench.parent.joinpath(testBench.stem + suffix)
        if candidate.exists():
            return candidate
    return None


def getIncludeFiles(testBench: pathlib.Path) -> list[str]:
    """Return the list of source files to include when compiling a testbench, as specified by the testbench's include config file."""
    includeFile = findIncludeConfigFile(testBench)
    if includeFile is None:
        print(f"no include file found for {testBench} (tried suffixes: {getIncludeSuffixes()})")
        sys.exit(1)
    with open(includeFile, 'r') as f:
        rawConfig: object = json.load(f)
    try:
        includeConfig = IncludeConfig.validateIncludeConfig(rawConfig)
    except ValueError as error:
        print(f"invalid include config format in {includeFile}: {error}")
        sys.exit(1)

    includeEntries = includeConfig["include"]

    includeFiles = []
    for entry in includeEntries:
        p = pathlib.Path(entry)
        if not p.is_absolute():
            p = testBench.parent.joinpath(p)
        includeFiles.append(str(p))

    # Ensure the testbench itself is present once, even if omitted from include config.
    tbPath = str(testBench)
    if tbPath not in includeFiles:
        includeFiles.append(tbPath)

    return includeFiles


def compileTestbench(testBench: pathlib.Path) -> pathlib.Path:
    """Compile a testbench along with every other source file.

    This mirrors the Makefile which uses all of $(SRCS) as inputs so that
    modules defined in other files (e.g. counter_4bit.v) are visible when
    elaborating the testbench.
    """
    out = testBench.with_suffix(".out")
    vcd = testBench.with_suffix(".vcd")
    
    sources = getIncludeFiles(testBench)

    # include the VCD filename quoted, similar to how the Makefile did it
    cmd = (
        [
            "iverilog",
            "-g2012",
            f'-DVCD_FILE="{vcd}"',
            "-o",
            str(out),
        ]
        + sources
    )
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)
    return out


def simulateTestBench(out: pathlib.Path) -> None:
    cmd = [
        "vvp",
        str(out),
    ]
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)


def openWave(vcd: pathlib.Path) -> None:
    cmd = [
        "gtkwave",
        str(vcd),
    ]
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)


def checkInstallConfigJson() -> None:
    if pathlib.Path("install.config.json").exists() == False:
        print("install.config.json not found")
        print("This likely means you are trying to run the install or uninstall option from the directory that that the framework was installed into.")
        sys.exit(1)


def getFrameworkFiles() -> list[str]:
    with open('install.config.json', 'r') as f:
        rawConfig: object = json.load(f)
    try:
        installConfig = InstallConfig.validateInstallConfig(rawConfig)
        return installConfig['frameworkFiles']
    except ValueError as error:
        print(f"invalid install config: {error}")
        sys.exit(1)


def install(installDirectory: pathlib.Path) -> None:

    checkInstallConfigJson()

    frameworkFiles = getFrameworkFiles()
    
    installDirectory.mkdir(parents=True, exist_ok=True)
    for item in frameworkFiles:
        src = pathlib.Path(item)
        dest = installDirectory.joinpath(src.name)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "*.out", "*.vcd", "*.gtkw", "*.sav"))
        else:
            shutil.copy2(src, dest)
    with open(installDirectory.joinpath(".verilog_framework_installed"), "w") as f:
        f.write("\n".join(frameworkFiles))
    print("installed to", installDirectory)


def uninstall(installDirectory: pathlib.Path) -> None:
    checkInstallConfigJson()
    
    frameworkFiles = getFrameworkFiles()
    
    for item in frameworkFiles:
        target = installDirectory.joinpath(item)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
    try:
        installDirectory.joinpath(".verilog_framework_installed").unlink()
    except FileNotFoundError:
        pass
    print("uninstalled from", installDirectory)


def clean() -> None:
    for testBench in getTestbenches():
        outFile = testBench.with_suffix(".out")
        vcdFile = testBench.with_suffix(".vcd")
        for file in (outFile, vcdFile):
            if file.exists():
                file.unlink()
    print("clean complete")


def getAssociatedTestBenches(changedSourceFile: pathlib.Path, testBenches: list[pathlib.Path]) -> list[pathlib.Path]:
    """Return testbenches affected by a changed source, testbench, or include config file."""
    changedSourceResolved = changedSourceFile.resolve()
    associatedTestBenches: list[pathlib.Path] = []
    for testBench in testBenches:
        testBenchResolved = testBench.resolve()
        if changedSourceResolved == testBenchResolved:
            associatedTestBenches.append(testBench)
            continue

        includeConfigFile = findIncludeConfigFile(testBench)
        if includeConfigFile is not None and changedSourceResolved == includeConfigFile.resolve():
            associatedTestBenches.append(testBench)
            continue

        includeFiles: list[pathlib.Path] = []
        for includePath in getIncludeFiles(testBench):
            includeFiles.append(pathlib.Path(includePath).resolve())
        # getIncludeFiles includes the testbench itself; we only care about non-testbench dependencies.
        dependencyFiles: list[pathlib.Path] = []
        for includePath in includeFiles:
            if includePath != testBenchResolved:
                dependencyFiles.append(includePath)
        if changedSourceResolved in dependencyFiles:
            associatedTestBenches.append(testBench)
    return associatedTestBenches


def watch() -> None:
    """Watch source, testbench, and include config files and rebuild affected testbenches on save."""
    testBenches = getTestbenches()
    watchedSources = getSources()
    includeConfigFiles: list[pathlib.Path] = []
    for testBench in testBenches:
        includeConfigPath = findIncludeConfigFile(testBench)
        if includeConfigPath is not None:
            includeConfigFiles.append(includeConfigPath)
    watchedPaths = watchedSources + includeConfigFiles
    sourceMtimes: dict[pathlib.Path, float] = {}
    for sourceFile in watchedPaths:
        if sourceFile.exists():
            sourceMtimes[sourceFile] = sourceFile.stat().st_mtime

    print(f"watching {len(watchedPaths)} files for changes...")
    while True:
        time.sleep(1.0)
        testBenches = getTestbenches()
        currentSources = getSources()
        currentIncludeConfigFiles: list[pathlib.Path] = []
        for testBench in testBenches:
            includeConfigPath = findIncludeConfigFile(testBench)
            if includeConfigPath is not None:
                currentIncludeConfigFiles.append(includeConfigPath)
        currentWatchedPaths = currentSources + currentIncludeConfigFiles
        for sourceFile in currentWatchedPaths:
            if sourceFile.exists() and sourceFile not in sourceMtimes:
                sourceMtimes[sourceFile] = sourceFile.stat().st_mtime

        changedSources: list[pathlib.Path] = []
        for sourceFile in currentWatchedPaths:
            if not sourceFile.exists():
                continue
            currentMtime = sourceFile.stat().st_mtime
            lastMtime = sourceMtimes.get(sourceFile)
            if lastMtime is None:
                sourceMtimes[sourceFile] = currentMtime
                continue
            if currentMtime > lastMtime:
                sourceMtimes[sourceFile] = currentMtime
                changedSources.append(sourceFile)

        for changedSourceFile in changedSources:
            associatedTestBenches = getAssociatedTestBenches(changedSourceFile, testBenches)
            if not associatedTestBenches:
                continue
            print(f"change detected: {changedSourceFile}")
            for testBench in associatedTestBenches:
                print(f"rebuilding and simulating {testBench}")
                outFile = compileTestbench(testBench)
                simulateTestBench(outFile)


def main() -> None:
    parser = argparse.ArgumentParser(description="Python build script for verilog project")
    parser.add_argument("target", nargs="?", default="compile", help="one of compile, simulate, waveform, watch, clean, install, uninstall")
    parser.add_argument("--dir", default="..", help="installation directory")
    args = parser.parse_args()

    target = cast(TargetName | str, args.target)

    testBenches = getTestbenches()

    if not testBenches and target in ("compile", "simulate", "waveform", "watch"):
        print("no testbenches found")
        sys.exit(1)

    match target:
        case "compile":
            for testBench in testBenches:
                compileTestbench(testBench)
        case "simulate":
            for testBench in testBenches:
                out = testBench.with_suffix(".out")
                if not out.exists():
                    compileTestbench(testBench)
                simulateTestBench(out)
        case "waveform":
            # replicate Makefile behaviour: build & run first TB if needed
            if testBenches:
                testBench = testBenches[0]
                firstVcd = testBench.with_suffix(".vcd")
                out = testBench.with_suffix(".out")
                if not firstVcd.exists():
                    # compile and run the tb to generate the VCD
                    if not out.exists():
                        compileTestbench(testBench)
                    simulateTestBench(out)
                openWave(firstVcd)
        case "watch":
            watch()
        case _ if target.startswith("wave-"):
            name = target.split("-", 1)[1]
            for testBench in testBenches:
                candidateNames = {
                    testBench.stem,
                    testBench.name,
                    str(testBench),
                    testBench.as_posix(),
                }
                if name in candidateNames:
                    openWave(testBench.with_suffix(".vcd"))
                    break
            else:
                print("no such testbench", name)
        case "install":
            install(pathlib.Path(args.dir))
        case "uninstall":
            uninstall(pathlib.Path(args.dir))
        case "clean":
            clean()
        case _:
            parser.print_help()

if __name__ == "__main__":
    main()
