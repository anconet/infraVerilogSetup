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

def getBuildConfig():
    with open('build.config.json', 'r') as f:
        return json.load(f)


def getSourceDirectory():
    return pathlib.Path(getBuildConfig()['sourceDirectory'])


def getTestbenchSuffixes():
    return getBuildConfig().get('testbenchSuffixes', ['_tb', '.test'])


def getIncludeSuffixes():
    return getBuildConfig().get('includeSuffixes', ['.include.json'])


def getVerilogSuffixes():
    return getBuildConfig().get('verilogSuffixes', ['.sv', '.v'])


def getSources(sourceDirectory: pathlib.Path):
    # rglob returns generators; concatenate by converting each to a list first
    sources = []
    for suffix in getVerilogSuffixes():
        sources += list(sourceDirectory.rglob(f"*{suffix}"))
    return sources


def findTestbenches(sourceDirectory: pathlib.Path, patterns: list = None):
    if patterns is None:
        patterns = getTestbenchSuffixes()
    return [p for p in getSources(sourceDirectory) if any(pat in p.name for pat in patterns)]


def compileTestbench(testBench: pathlib.Path, sourceDirectory: pathlib.Path):
    """Compile a testbench along with every other source file.

    This mirrors the Makefile which uses all of $(SRCS) as inputs so that
    modules defined in other files (e.g. counter_4bit.v) are visible when
    elaborating the testbench.
    """
    out = testBench.with_suffix(".out")
    vcd = testBench.with_suffix(".vcd")
    includeFile = None
    for suffix in getIncludeSuffixes():
        candidate = testBench.parent / (testBench.stem + suffix)
        if candidate.exists():
            includeFile = candidate
            break
    if includeFile is None:
        print(f"no include file found for {testBench} (tried suffixes: {getIncludeSuffixes()})")
        sys.exit(1)
    with open(includeFile, 'r') as f:
        includeConfig = json.load(f)

    if not isinstance(includeConfig, dict) or not isinstance(includeConfig.get("include"), list):
        print(f"invalid include config format in {includeFile}")
        sys.exit(1)

    includeEntries = includeConfig["include"]

    sources = []
    for entry in includeEntries:
        p = pathlib.Path(entry)
        if not p.is_absolute():
            p = testBench.parent / p
        sources.append(str(p))

    # Ensure the testbench itself is present once, even if omitted from include config.
    tbPath = str(testBench)
    if tbPath not in sources:
        sources.append(tbPath)

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


def runTb(out: pathlib.Path):
    cmd = [
        "vvp",
        str(out),
    ]
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)


def openWave(vcd: pathlib.Path):
    cmd = [
        "gtkwave",
        str(vcd),
    ]
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)


def checkInstallConfigJson():
    if pathlib.Path("install.config.json").exists() == False:
        print("install.config.json not found")
        print("This likely means you are trying to run the install or uninstall option from the directory that that the framework was installed into.")
        sys.exit(1)


def getFrameworkFiles():
    with open('install.config.json', 'r') as f:
        installConfig = json.load(f)
    return installConfig['frameworkFiles']


def install(installDirectory: pathlib.Path):

    checkInstallConfigJson()

    frameworkFiles = getFrameworkFiles()
    
    installDirectory.mkdir(parents=True, exist_ok=True)
    for item in frameworkFiles:
        src = pathlib.Path(item)
        dest = installDirectory / src.name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "*.out", "*.vcd", "*.gtkw", "*.sav"))
        else:
            shutil.copy2(src, dest)
    with open(installDirectory / ".verilog_framework_installed", "w") as f:
        f.write("\n".join(frameworkFiles))
    print("installed to", installDirectory)


def uninstall(installDirectory: pathlib.Path):
    checkInstallConfigJson()
    
    frameworkFiles = getFrameworkFiles()
    
    for item in frameworkFiles:
        target = installDirectory / item
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
    try:
        (installDirectory / ".verilog_framework_installed").unlink()
    except FileNotFoundError:
        pass
    print("uninstalled from", installDirectory)


def clean(sourceDirectory: pathlib.Path):
    for testBench in findTestbenches(sourceDirectory):
        outFile = testBench.with_suffix(".out")
        vcdFile = testBench.with_suffix(".vcd")
        for file in (outFile, vcdFile):
            if file.exists():
                file.unlink()
    print("clean complete")


def main():
    parser = argparse.ArgumentParser(description="Python build script for verilog project")
    parser.add_argument("target", nargs="?", default="compile", help="one of compile, simulate, waveform, clean, install, uninstall")
    parser.add_argument("--dir", default="..", help="installation directory")
    args = parser.parse_args()

    sourceDirectory = getSourceDirectory()

    testBenches = findTestbenches(sourceDirectory)

    if not testBenches and args.target in ("compile", "simulate", "waveform"):
        print("no testbenches found")
        sys.exit(1)

    match args.target:
        case "compile":
            for testBench in testBenches:
                compileTestbench(testBench, sourceDirectory)
        case "simulate":
            for testBench in testBenches:
                out = testBench.with_suffix(".out")
                if not out.exists():
                    compileTestbench(testBench, sourceDirectory)
                runTb(out)
        case "waveform":
            # replicate Makefile behaviour: build & run first TB if needed
            if testBenches:
                testBench = testBenches[0]
                firstVcd = testBench.with_suffix(".vcd")
                out = testBench.with_suffix(".out")
                if not firstVcd.exists():
                    # compile and run the tb to generate the VCD
                    if not out.exists():
                        compileTestbench(testBench, sourceDirectory)
                    runTb(out)
                openWave(firstVcd)
        case _ if args.target.startswith("wave-"):
            name = args.target.split("-", 1)[1]
            for testBench in testBenches:
                if testBench.stem == name:
                    openWave(testBench.with_suffix(".vcd"))
                    break
            else:
                print("no such testbench", name)
        case "install":
            install(pathlib.Path(args.dir))
        case "uninstall":
            uninstall(pathlib.Path(args.dir))
        case "clean":
            clean(sourceDirectory)
        case _:
            parser.print_help()

if __name__ == "__main__":
    main()
