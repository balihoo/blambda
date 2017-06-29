"""
Run unittests for a given set of functions
"""
import os
import subprocess as sp
import sys

from termcolor import cprint

from .utils import env_manager
from .utils.findfunc import find_manifest
from .utils.lambda_manifest import LambdaManifest


def fancy_print(header, msg):
    cprint(header + ": ", 'blue', end='')
    cprint(msg, 'yellow')


def setup_parser(parser):
    parser.add_argument('function_names', nargs='*', type=str, help='the base(s) name of the function')


def run(args):
    original_path = list(sys.path)
    for func in args.function_names:
        manifest_filename = find_manifest(func)
        manifest = LambdaManifest(manifest_filename)
        env = env_manager.EnvManager(manifest.runtime)

        if args.verbose:
            fancy_print("Python", env.python)
            fancy_print("Lib dir", manifest.lib_dir)

        os.chdir(manifest.basedir)
        os.environ['PYTHONPATH'] = ':'.join([manifest.lib_dir] + original_path)
        if args.verbose > 1:
            fancy_print("PYTHONPATH", os.environ['PYTHONPATH'])

        test_file = os.path.join(manifest.basedir, f'test_{manifest.function_name}.py')

        fancy_print("Testing", test_file)
        sp.call([env.python, '-m', 'unittest', test_file])
        print("")
