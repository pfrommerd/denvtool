# Installation and Basic Usage

Using denvtool is easy, to install:
```bash
pip install git+https://github.com/pfrommerd/denvtool.git
```
Then generate a new project with
```bash
denvtool new
```
in the root directory of the project folder.

Denvtool has several steps:
 1. Run docker/config.py to prompt the user for the environment configuration
 2. Generate the Dockerfiles using the .templates in the docker folder
 3. Build the container
 4. Start the container


To generate the environment files, build the container, and start, use
```
denvtool start
```
Once started, get a shell in the running container using
```
denvtool shell
```
I highly recommend using the VSCode Dev Containers extension to attach to the running container.
You can use Ctrl + Shift + P in VSCode to bring up the command menu and search for "Attach to Running Container"

### More operations

You can explicitly re-generate the configuration or Dockerfiles using
```
denvtool config
```
and
```
denvtool gen
```
To just build the container (without starting) you can use
```
denvtool build
```
To shut down the container, use
```
denvtool stop
```
To delete all files relating to a configuration (including the stored home directory volume), use
```
denvtool purge
```
