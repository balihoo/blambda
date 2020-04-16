import os

from termcolor import cprint

from .base import spawn, json_fileload, die
from .lambda_manifest import LambdaManifest


def find_manifest(function_name, fail_if_missing=False):
    """Find an individual manifest given a function name"""
    search_root = get_search_root()
    cprint(f'Search root: {search_root}', 'yellow') 
    manifests = find_all_manifests(search_root)
    print(manifests)
    matching = [m for m in manifests if function_name in (m.short_name, m.full_name, f'{m.group}/{m.short_name}')]
    if not matching:
        if fail_if_missing:
            die(f"Couldn't find {function_name}")
        return None

    # prefer the manifest in pwd, if possible
    if len(matching) > 1:
        for match in matching:
            if match.basedir.samefile('.'):
                return match

    # otherwise just return the first available match
    return matching[0]


def find_manifests(function_names):
    """Find a set of manifests given a set of function name"""
    search_root = get_search_root()
    cprint(f'Search root: {search_root}', 'yellow') 
    manifests = find_all_manifests(search_root)
    print(manifests)

    # get manifests where either short_name or full_name is in the function_names list
    return [m for m in manifests
            if any(name in function_names for name in (m.short_name, m.full_name, f'{m.group}/{m.short_name}'))]


def find_all_manifests(root, verbose=False):
    """Find all manifests in a given directory/root"""
    json_files = _all_json_files(root)
    manifests = (_load_manifest(json_file, verbose) for json_file in json_files)
    return [m for m in manifests if m]


def _all_json_files(root):
    return [os.path.join(r, f) for r, _, fs in os.walk(root) for f in fs if f.endswith('.json')]


def get_search_root():
    (ret, stdout, stderr) = spawn("git rev-parse --show-toplevel")
    if ret == 0:
        return stdout[0]
    return os.getcwd()


def get_runtime(manifest_path):
    try:
        manifest = json_fileload(manifest_path)
        if type(manifest) == dict:
            return manifest.get('options').get('Runtime')
    except ValueError as e:
        cprint("{} is not valid json: {}".format(manifest_path, e), 'red')


def _load_manifest(filename, verbose=True):
    try:
        return LambdaManifest(filename, parse_json=True)
    except ValueError as e:
        if verbose:
            cprint(e, 'red')


def all_remote_functions(region="us-east-1"):
    import boto3
    lmb = boto3.client('lambda', region_name=region)
    functions = {}

    def getfs(marker=None):
        lf = lmb.list_functions
        response = lf(Marker=marker) if marker else lf()
        functions.update({f['FunctionName']: f['Description'] for f in response['Functions']})
        if 'NextMarker' in response:
            getfs(response['NextMarker'])

    getfs()
    return functions
