import sys
import argparse
from .util import AttrMap
from jinja2 import Environment, FileSystemLoader

import shutil
from pathlib import Path
from rich import print
from platformdirs import user_cache_dir

import os
import subprocess
import json
import toml
import importlib.util

def get_project_dir():
    pdir = Path(os.getcwd())
    while not (pdir / 'docker' / 'config.py').exists():
        pdir = pdir.parent
        if str(pdir) == '/':
            return None
    return pdir

ENVS_DIR = Path(user_cache_dir("denvtool"))
USER = os.environ.get('USER')
UID = subprocess.check_output(['id', '-u']).decode().strip()
GID = subprocess.check_output(['id', '-g']).decode().strip()

# Utility functions templates can use

def read_requirements(path):
    requirements = {}
    with open(path) as f:
        for l in f.readlines():
            l = l.strip()
            if l.startswith('#') or not l:
                continue
            pkg, ver = l.split('==')
            parts = ver.split("+")
            ver = parts[0]
            extras = parts[1:]
            requirements[pkg] = {"version": ver, "extras": extras}
    return AttrMap.make_recursive(requirements)

def read_poetry_project(path):
    lock_path = path / "poetry.lock"
    project_path = path / "pyproject.toml"
    requirements = {}
    with open(project_path) as f:
        parsed_project = toml.load(f)
    for name, p in parsed_project["tool"]["poetry"]["dependencies"].items():
        if name == "python":
            continue
        if isinstance(p, dict):
            version = p.get("version", None)
            sub_path = p.get("path", None)
            if sub_path:
                sub_deps = read_poetry_project(path / sub_path)
                requirements.update(sub_deps)
                continue
        else:
            version = p
        if version is not None:
            version = version.lstrip("^~")
        requirements[name] = {"version": version, "extras": []}
    if lock_path.exists():
        with open(lock_path) as f:
            parsed_lock = toml.load(f)
        for p in parsed_lock["package"]:
            if p["name"] in requirements:
                requirements[p["name"]]["version"] = p["version"]
    return AttrMap.make_recursive(requirements)

def requirements_install_opts(requirements):
    def format_package(name, p):
        target = name
        if p["extras"]:
            target = target + "[" + ",".join(p["extras"]) + "]"
        version = p["version"]
        if version:
            return f"{target}=={p.version}"
        else:
            return target
    return " ".join([format_package(name, p) for name, p in requirements.items()])

def filter_in(*args):
    args = set(args)
    return lambda x, *oargs: x in args

def filter_not_in(*args):
    args = set(args)
    return lambda x, *oargs: x not in args

def debug_print(*args):
    print(*args)
    return ""

TEMPLATE_GLOBALS = {
    "read_requirements": read_requirements,
    "read_poetry_project": read_poetry_project,
    "requirements_install_opts": requirements_install_opts,
    "filter_in": filter_in,
    "filter_not_in": filter_not_in,
    "debug_print": debug_print
}

def get_path(env_name):
    return ENVS_DIR / env_name

def get_config(env_name):
    config_path = get_path(f"{env_name}.config")
    if not config_path.exists():
        do_config(env_name)
    with open(config_path) as f:
        config = json.load(f, object_hook=AttrMap)
    return config

def get_env(env_name):
    env_path = get_path(env_name)
    if not env_path.exists():
        do_gen(env_name)
    return env_path

def do_new(env_name):
    cwd = Path(os.getcwd())
    print(f"[blue]Making new denvtool project at [/blue][green]{cwd}[/green]")
    templates_dir = Path(__file__).parent / "templates"
    import inquirer
    template_name = inquirer.prompt([
        inquirer.List('template_name', message="What template should we use?",
            choices=list(x.name for x in templates_dir.iterdir())
        )
    ])["template_name"]
    # copy the template to the current directory /docker
    template_dir = templates_dir / template_name
    print(f"[blue]Initializing template from[/blue] [green]{template_dir}[/green]")
    for p in template_dir.iterdir():
        src = p
        dest = cwd / p.name
        if src.is_file():
            shutil.copy(src, dest)
        else:
            shutil.copytree(src, dest)

# import the project config.py to get the config
def do_config(env_name):
    config_path = get_path(f"{env_name}.config")
    pdir = get_project_dir()
    config_py_path = pdir / 'docker' / 'config.py'
    with open(config_py_path, 'r') as f:
        config_py = f.read()
    config_mod = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("config", config_py_path)
    )
    # load the config into the module
    exec(config_py, config_mod.__dict__)
    config = config_mod.config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

def do_gen(env_name):
    config = get_config(env_name)
    env_path = get_path(env_name)
    if env_path.exists():
        shutil.rmtree(env_path)
    env_path.mkdir(parents=True)
    print(f"Generating environment config for [blue]{env_name}[/blue]")

    pdir = get_project_dir()
    base_dir = pdir / 'docker'

    template_args = {
        'env_name': env_name,
        'user': USER, 'uid': UID, 'gid': GID,
        'project_dir': pdir,
        'env_name': env_name,
        'env_path': env_path,
        'env_image': f"{env_name}-env",
        'config': config
    }

    environment = Environment(loader=FileSystemLoader(base_dir))
    templates = base_dir.glob('*.template')
    for template_path in templates:
        filename = template_path.name.removesuffix('.template')
        # ignore devcontainer.json
        # that is handled separately
        if filename == 'devcontainer.json':
            continue
        template = environment.get_template(f"{filename}.template")
        template.globals.update(TEMPLATE_GLOBALS)
        content = template.render(**template_args)
        dest = env_path / filename
        with open(dest, 'w') as f:
            f.write(content)
        print(f"Wrote [green]{filename}[/green] to [green]{dest}[/green]")
    
    # generate a vscode devcontainer info file
    # into .devcontainer/devcontainer.json
    dc_template = environment.get_template('devcontainer.json.template')
    if dc_template is not None:
        dc_template.globals.update(TEMPLATE_GLOBALS)
        dc_path = pdir / '.devcontainer' / 'devcontainer.json'
        dc_path.parent.mkdir(parents=True, exist_ok=True)
        dc_content = dc_template.render(**template_args)
        with open(dc_path, 'w') as f:
            f.write(dc_content)
        print(f"Wrote [green]devcontainer.json[/green] to [green]{dc_path}[/green]")
    
    for f in config.context:
        src = pdir / f
        dest = env_path / f
        if src.exists():
            if src.is_file():
                shutil.copy(src, dest)
            else:
                shutil.copytree(src, dest)
            print(f"Copied [green]{src}[/green] to [green]{dest}[/green]")
        else:
            print(f"[red]Could not find context file:[/red] [blue]{src}[/blue]")

def do_build(env_name):
    env_path = get_env(env_name)
    subprocess.run(['docker', 'compose', 'build'], cwd=env_path)

def do_start(env_name):
    env_path = get_env(env_name)
    subprocess.run(['docker', 'compose', 'build'],
        cwd=env_path)
    subprocess.run(['docker', 'compose', 'up',
        '--remove-orphans', '-d'], cwd=env_path)

def do_stop(env_name):
    env_path = get_env(env_name)
    subprocess.run(['docker', 'compose', 'down'], cwd=env_path)

def do_purge(env_name):
    env_path = get_path(env_name)
    if env_path.exists():
        subprocess.run(['docker', 'compose', 'down', '-v'], cwd=env_path)
        shutil.rmtree(env_path)
    # delete any config info if it exists
    config_path = get_path(f"{env_name}.config")
    config_path.unlink(missing_ok=True)

def do_shell(env_name):
    env_path = get_env(env_name)
    running = subprocess.check_output(
        ["docker", "compose", "ps", "-q", "env"],
        cwd=env_path
    ).decode().strip() != ""
    if not running:
        do_start(env_name)
    config = get_config(env_name)
    subprocess.run(['docker', 'compose', 'exec', 
        'env', config.shell
    ], cwd=env_path)

COMMANDS = {
    'new': do_new,
    'config': do_config,
    'gen': do_gen,
    'build': do_build,
    'start': do_start,
    'stop': do_stop,
    'purge': do_purge,
    'shell': do_shell
}

def run():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')
    for command in COMMANDS:
        subparsers.add_parser(command, help=COMMANDS[command].__doc__)
    parser.add_argument('env_name',
        help='Name of the environment',
        default=None,
        nargs='?'
    )
    args = parser.parse_args()
    env_name = args.env_name
    if args.command is None:
        print(f"[red]No command provided[/red]")
        return 
    elif args.command not in COMMANDS:
        print(f"[red]Unknown command:[/red] [blue]{args.command}[/blue]")
        return
    if args.command != 'new' and env_name is None:
        pdir = get_project_dir()
        if pdir == None:
            print(f"[red]No project directory found[/red]")
            sys.exit(1)
        env_name = pdir.name
    cmd = COMMANDS[args.command]
    cmd(env_name)

if __name__=='__main__':
    run()
