#!/usr/bin/env python3
"""Simple Python replacement for the Makefile targets.

Usage examples:
    ./build.py all
    ./build.py run
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

def get_source_directory():
    with open('build.config.json', 'r') as f:
        config = json.load(f)
    return pathlib.Path(config['sourceDirectory'])


def find_sources(sourceDirectory: pathlib.Path):
    # rglob returns a generator; concatenate by converting to lists first
    svs = list(sourceDirectory.rglob("*.sv"))
    vs  = list(sourceDirectory.rglob("*.v"))
    return svs + vs


def find_tbs(sourceDirectory: pathlib.Path):
    return [p for p in find_sources(sourceDirectory) if "_tb" in p.name or ".test" in p.name]


def basename(p: pathlib.Path) -> str:
    return p.with_suffix("")


def compile_tb(tb: pathlib.Path, sourceDirectory: pathlib.Path):
    """Compile a testbench along with every other source file.

    This mirrors the Makefile which uses all of $(SRCS) as inputs so that
    modules defined in other files (e.g. counter_4bit.v) are visible when
    elaborating the testbench.
    """
    out = tb.with_suffix(".out")
    vcd = tb.with_suffix(".vcd")
    # gather every Verilog/SystemVerilog source so the tb can reference them
    # the tb itself will be added explicitly later to avoid duplicates
    sources = [str(p) for p in find_sources(sourceDirectory) if p != tb]
    # include the VCD filename quoted, similar to how the Makefile did it
    cmd = [
        "iverilog",
        "-g2012",
        f'-DVCD_FILE="{vcd}"',
        "-o",
        str(out),
    ] + sources + [str(tb)]
    print("compiling", tb, "with", cmd)
    subprocess.check_call(cmd)
    return out


def run_tb(out: pathlib.Path):
    print("running", out)
    subprocess.check_call(["vvp", str(out)])


def open_wave(vcd: pathlib.Path):
    subprocess.check_call(["gtkwave", str(vcd)])


def check_installConfigJson():
    if pathlib.Path("install.config.json").exists() == False:
        print("install.config.json not found")
        print("This likely means you are trying to run the install or uninstall option from the directory that that the framework was installed into.")
        sys.exit(1)


def get_framework_files():
    with open('install.config.json', 'r') as f:
        install_config = json.load(f)
    return install_config['frameworkFiles']


def install(dir_: pathlib.Path):

    check_installConfigJson()

    frameworkFiles = get_framework_files()
    
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
    check_installConfigJson()
    
    frameworkFiles = get_framework_files()
    
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
    for tb in find_tbs(sourceDirectory):
        out = tb.with_suffix(".out")
        vcd = tb.with_suffix(".vcd")
        for f in (out, vcd):
            if f.exists():
                f.unlink()
    print("clean complete")


def main():
    parser = argparse.ArgumentParser(description="Python build script for verilog project")
    parser.add_argument("target", nargs="?", default="all", help="one of all, run, waveform, clean, install, uninstall")
    parser.add_argument("--dir", default="..", help="installation directory")
    args = parser.parse_args()

    sourceDirectory = get_source_directory()

    testBenches = find_tbs(sourceDirectory)

    if not testBenches and args.target in ("all", "run", "waveform"):
        print("no testbenches found")
        sys.exit(1)

    if args.target == "all":
        for tb in testBenches:
            compile_tb(tb, sourceDirectory)
    elif args.target == "run":
        for tb in testBenches:
            out = tb.with_suffix(".out")
            if not out.exists():
                compile_tb(tb, sourceDirectory)
            run_tb(out)
    elif args.target == "waveform":
        # replicate Makefile behaviour: build & run first TB if needed
        if testBenches:
            tb = testBenches[0]
            first_vcd = tb.with_suffix(".vcd")
            out = tb.with_suffix(".out")
            if not first_vcd.exists():
                # compile and run the tb to generate the VCD
                if not out.exists():
                    compile_tb(tb, sourceDirectory)
                run_tb(out)
            open_wave(first_vcd)
    elif args.target.startswith("wave-"):
        name = args.target.split("-", 1)[1]
        for tb in testBenches:
            if tb.stem == name:
                open_wave(tb.with_suffix(".vcd"))
                break
        else:
            print("no such testbench", name)
    elif args.target == "install":
        install(pathlib.Path(args.dir))
    elif args.target == "uninstall":
        uninstall(pathlib.Path(args.dir))
    elif args.target == "clean":
        clean(sourceDirectory)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
