from __future__ import print_function

import argparse
import shutil
import subprocess as sp

import os

from termcolor import cprint
from .utils import env_manager
from .utils.lambda_manifest import LambdaManifest


def read_function_names_from_file(filename):
    with open(filename) as f:
        return {line.strip() for line in f}


def default_lambda_functions_search_dir():
    try:
        return sp.check_output('git rev-parse --show-toplevel', shell=True, universal_newlines=True).strip()
    except sp.CalledProcessError:
        return '.'


def find_function_manifest(func_name, search_root=default_lambda_functions_search_dir()):
    for (root, dirs, files) in os.walk(search_root):
        for file in files:
            if file == func_name + '.json':
                return os.path.join(root, file)


def main(args=None):
    parser = argparse.ArgumentParser("prepare development of python lambda functions")
    parser.add_argument('function_names', nargs='*', type=str, help='the base name of the function')
    parser.add_argument('-c', '--clean', help='clean environment', action='store_true')
    parser.add_argument('-p', '--prod', help='production. Install no dev deps', action='store_true')
    parser.add_argument('-e', '--echo-env', help='return which blambda virtualenv is used', action='store_true')
    parser.add_argument('--file', type=str, help='filename containing function names')
    args = parser.parse_args(args)

    func_names = set(args.function_names)
    if args.file:
        func_names += read_function_names_from_file(args.file)
        cprint("read {} from {}".format(func_names, args.file), 'blue')

    for func_name in func_names:
        manifest_filename = find_function_manifest(func_name)
        if not manifest_filename:
            cprint("unable to find " + func_name, 'red')
            exit(1)
        else:
            manifest = LambdaManifest(manifest_filename)
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


if __name__ == '__main__':
    main()
