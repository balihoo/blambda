"""
Execute a command locally
"""
import importlib.util
import json
import os
import sys

from termcolor import cprint

from .local_test import fancy_print
from .utils import env_manager
from .utils.findfunc import find_manifest


def setup_parser(parser):
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--payload', type=str, help="file containing json params to send to the function", default=None)


def import_lambda_function_from_file(path):
    spec = importlib.util.spec_from_file_location('the_lambda_function', path)
    module_ = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module_)
    return module_.lambda_handler


def run(args):
    payload = args.payload
    if payload is None:
        cprint("reading payload from stdin...", 'yellow')
        payload = json.loads(sys.stdin.read())
    else:
        with open(payload, 'r') as f:
            payload = json.load(f)

    manifest = find_manifest(args.function_name, fail_if_missing=True)
    env = env_manager.EnvManager(manifest.runtime)

    sys.path.insert(0, str(manifest.lib_dir))
    sys.path.insert(0, str(manifest.basedir))

    py_file = os.path.join(manifest.basedir, manifest.short_name + '.py')

    if args.verbose:
        fancy_print("Python", env.python)
        fancy_print("Lib dir", manifest.lib_dir)
        fancy_print("sys.path", sys.path)

    func = import_lambda_function_from_file(py_file)
    cprint("Calling " + py_file, 'green')

    try:
        retval = func(payload, None)
    except Exception as e:
        cprint(f"Error executing lambda function!\n{e}")
    else:
        try:
            color = 'blue' if retval.get('status') == 'SUCCESS' else 'red'
        except Exception as e:
            color = 'red'
        cprint(json.dumps(retval, indent=4), color)
