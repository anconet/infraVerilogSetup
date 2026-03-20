# infraVerilogSetup
This is a repo for setting up a verilog project.

The really interesting concepts were inspirded by [Igor Freire](https://igorfreire.com.br/blog/)

## How to use
1) Create a project directory.
2) Add this repo as a submodule
```bash
git add submodule https://github.com/anconet/infraVerilogSetup.git ./install
```
3) Run the install
```bash
./install/build.py install
```

The install routine will copy over a .devcontainer directory. This directory contains configuration for a docker container that we can use for development. 

In VSCode
* Add the Microsoft Dev Containers extention. 
    * This thing seems to take care of all of the Docker Gobbledegook...
* Low left Blue Remote area
    * Left click
    * "Open in DevContainer"

## Options

## How to use
Run the --help option to see build.py options
```bash
./build.py --help
```
