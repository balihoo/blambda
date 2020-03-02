"""
create a new lambda function
"""
import json
from collections import namedtuple
from pathlib import Path

from .utils.base import die
from .utils.lambda_manifest import LambdaManifest

LambdaRuntime = namedtuple('LambdaRuntime', ('manifest', 'extension', 'source_dir'))

runtimes = {
    'python27': LambdaRuntime('python2.7', '.py', 'python/src'),
    'python36': LambdaRuntime('python3.6', '.py', 'python/src'),
    'python37': LambdaRuntime('python3.7', '.py', 'python/src'),
    'python38': LambdaRuntime('python3.8', '.py', 'python/src'),
    'coffee': LambdaRuntime('nodejs4.3', '.coffee', 'node/src')
}


def setup_parser(parser):
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--nodir', help='do not create a directory', action='store_true')
    parser.add_argument('--runtime', default='python36', choices=runtimes.keys(), help='which lambda runtime '
                                                                                       '(default: %(default)s')


def is_project_root(path: Path):
    return (path / 'python' / 'src').is_dir() and (path / 'node' / 'src').is_dir()


def find_project_root():
    path = Path('.').absolute()
    while not is_project_root(path):
        path = path.parent
        if str(path) == path.anchor:
            die("Couldn't find intellij project .iml file!", 'red')
    return path


def lambda_function_name(function_name: str):
    """ validate user input and split out the parent directory """
    try:
        parent, name = function_name.split('/', 1)
        if '/' in name or parent[0].isdigit() or name[0].isdigit():
            die(f"Invalid lambda function name: {function_name}")
        return parent, name

    except ValueError:
        return function_name, function_name


def run(args):
    parent, function_name = lambda_function_name(args.function_name)
    runtime = runtimes[args.runtime]
    root = find_project_root()
    manifest = LambdaManifest(root / runtime.source_dir / parent / (function_name + '.json'))

    filename = manifest.path.with_suffix(runtime.extension)

    manifest_json = {
        "blambda": "manifest",
        "dependencies": {},
        "options": {
            "Description": args.function_name,
            "Timeout": 300,
            "Runtime": runtime.manifest
        },
        "permissions": [],
        "source files": [str(filename.name)]
    }

    manifest.path.parent.mkdir(parents=True, exist_ok=True)
    with manifest.path.open('w') as f:
        json.dump(manifest_json, f, indent=4, sort_keys=True)

    with filename.open('w') as f:
        if 'python' in args.runtime:
            f.write('def lambda_handler(event, context):\n    return event')
        else:
            f.write('exports.handler = (event, context) ->\n    event')
