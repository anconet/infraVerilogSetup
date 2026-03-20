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

def get_build_config():
    with open('build.config.json', 'r') as f:
        return json.load(f)


def get_source_directory():
    return pathlib.Path(get_build_config()['sourceDirectory'])


def getTestbenchSuffixes():
    return get_build_config().get('testbenchSuffixes', ['_tb', '.test'])


def getIncludeSuffixes():
    return get_build_config().get('includeSuffixes', ['.include.json'])


def find_sources(sourceDirectory: pathlib.Path):
    # rglob returns a generator; concatenate by converting to lists first
    svs = list(sourceDirectory.rglob("*.sv"))
    vs  = list(sourceDirectory.rglob("*.v"))
    return svs + vs


def findTestbenches(sourceDirectory: pathlib.Path, patterns: list = None):
    if patterns is None:
        patterns = getTestbenchSuffixes()
    return [p for p in find_sources(sourceDirectory) if any(pat in p.name for pat in patterns)]


def compileTestbench(testBench: pathlib.Path, sourceDirectory: pathlib.Path):
    """Compile a testbench along with every other source file.

    This mirrors the Makefile which uses all of $(SRCS) as inputs so that
    modules defined in other files (e.g. counter_4bit.v) are visible when
    elaborating the testbench.
    """
    out = testBench.with_suffix(".out")
    vcd = testBench.with_suffix(".vcd")
    include_file = None
    for suffix in getIncludeSuffixes():
        candidate = testBench.parent / (testBench.stem + suffix)
        if candidate.exists():
            include_file = candidate
            break
    if include_file is None:
        print(f"no include file found for {testBench} (tried suffixes: {getIncludeSuffixes()})")
        sys.exit(1)
    with open(include_file, 'r') as f:
        include_config = json.load(f)

    if not isinstance(include_config, dict) or not isinstance(include_config.get("include"), list):
        print(f"invalid include config format in {include_file}")
        sys.exit(1)

    include_entries = include_config["include"]

    sources = []
    for entry in include_entries:
        p = pathlib.Path(entry)
        if not p.is_absolute():
            p = testBench.parent / p
        sources.append(str(p))

    # Ensure the testbench itself is present once, even if omitted from include config.
    tb_path = str(testBench)
    if tb_path not in sources:
        sources.append(tb_path)

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


def run_tb(out: pathlib.Path):
    cmd = [
        "vvp",
        str(out),
    ]
    print("+", subprocess.list2cmdline(cmd))
    subprocess.check_call(cmd)


def open_wave(vcd: pathlib.Path):
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
        install_config = json.load(f)
    return install_config['frameworkFiles']


def install(dir_: pathlib.Path):

    checkInstallConfigJson()

    frameworkFiles = getFrameworkFiles()
    
    dir_.mkdir(parents=True, exist_ok=True)
    for item in frameworkFiles:
        src = pathlib.Path(item)
        dest = dir_ / src.name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "*.out", "*.vcd", "*.gtkw", "*.sav"))
        else:
            shutil.copy2(src, dest)
    with open(dir_ / ".verilog_framework_installed", "w") as f:
        f.write("\n".join(frameworkFiles))
    print("installed to", dir_)


def uninstall(dir_: pathlib.Path):
    checkInstallConfigJson()
    
    frameworkFiles = getFrameworkFiles()
    
    for item in frameworkFiles:
        target = dir_ / item
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
    try:
        (dir_ / ".verilog_framework_installed").unlink()
    except FileNotFoundError:
        pass
    print("uninstalled from", dir_)


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

    sourceDirectory = get_source_directory()

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
                run_tb(out)
        case "waveform":
            # replicate Makefile behaviour: build & run first TB if needed
            if testBenches:
                testBench = testBenches[0]
                first_vcd = testBench.with_suffix(".vcd")
                out = testBench.with_suffix(".out")
                if not first_vcd.exists():
                    # compile and run the tb to generate the VCD
                    if not out.exists():
                        compileTestbench(testBench, sourceDirectory)
                    run_tb(out)
                open_wave(first_vcd)
        case _ if args.target.startswith("wave-"):
            name = args.target.split("-", 1)[1]
            for testBench in testBenches:
                if testBench.stem == name:
                    open_wave(testBench.with_suffix(".vcd"))
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
