"""
prepare development of python lambda functions
"""
import shutil

import os

from termcolor import cprint

from .utils.findfunc import find_manifest
from .utils import env_manager


def read_function_names_from_file(filename):
    if not os.path.isfile(filename):
        return set()
    with open(filename) as f:
        return {line.strip() for line in f}


def setup_parser(parser):
    parser.add_argument('function_names', nargs='*', type=str, help='the base name of the function')
    parser.add_argument('-c', '--clean', help='clean environment', action='store_true')
    parser.add_argument('-p', '--prod', help='production. Install no dev deps', action='store_true')
    parser.add_argument('-e', '--echo-env', help='return which blambda virtualenv is used', action='store_true')
    parser.add_argument('--file', type=str, help='filename containing function names')


def run(args):
    func_names = set(args.function_names)
    if args.file:
        func_names |= read_function_names_from_file(args.file)
        cprint("read {} from {}".format(func_names, args.file), 'blue')

    for func_name in func_names:
        manifest = find_manifest(func_name)
        if not manifest:
            cprint("unable to find " + func_name, 'red')
            exit(1)
        else:
            if args.echo_env:
                env = env_manager.EnvManager(manifest.runtime)
                print(env.runtime.env_name)
                print(manifest.lib_dir)
            else:
                cprint("setting up " + func_name, 'blue')
                manifest.process_manifest(args.clean, args.prod)

    # copy activation script to pwd
    this_file_dir = os.path.dirname(os.path.abspath(__file__))
    shutil.copy(os.path.join(this_file_dir, 'blambda-env'), '.')
