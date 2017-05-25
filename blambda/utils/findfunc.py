import json

import os
from termcolor import cprint

from .base import spawn, json_fileload

try:
    import boto3
except ImportError:
    print("Unable to import boto")


def all_json_files(root):
    return [os.path.join(r, f) for r, _, fs in os.walk(root) for f in fs if f.endswith('.json')]


def split_path(path):
    (basedir, jsonfile) = os.path.split(path)
    (name, ext) = os.path.splitext(jsonfile)
    return basedir, name, ext


def find_manifest(pkgname, srcdir="."):
    return find_manifests([pkgname]).get(pkgname)


def find_manifests(pkgnames, verbose=True):
    """ return a dictionary keyed by pkgname with the found manifest's full path """
    (abspath, dirname) = (os.path.abspath, os.path.dirname)
    (ret, stdout, stderr) = spawn("git rev-parse --show-toplevel")
    root = stdout[0] if ret == 0 else os.getcwd()
    jsonfiles = all_json_files(root)

    def ensure_json(pkgname):
        return pkgname if pkgname.endswith(".json") else "{}.json".format(pkgname)

    def match(pkg, jsonfile):
        return jsonfile.endswith(ensure_json(pkg)) and is_manifest(jsonfile, verbose)

    return {p: j for p in pkgnames for j in jsonfiles if match(p, j)}


def get_runtime(manifest_path):
    try:
        manifest = json_fileload(manifest_path)
        if type(manifest) == dict:
            return manifest.get('options').get('Runtime')
    except ValueError as e:
        cprint("{} is not valid json: {}".format(manifest_path, e), 'red')


def is_manifest(path, verbose=True, raise_on_bad_json=False):
    try:
        # hacky exclusions of files over 10k
        if os.path.getsize(path) < 10000:
            with open(path) as f:
                manifest = None
                try:
                    manifest = json.load(f)
                except ValueError as e:
                    msg = "{} is not valid json: {}".format(path, e)
                    if raise_on_bad_json:
                        raise Exception(msg)
                    elif verbose:
                        cprint(msg, 'red')
                return type(manifest) == dict and manifest.get('blambda') == "manifest"
    except OSError as e:
        if verbose:
            cprint("unhandled exception processing {}".format(path), 'red')
    return False


def all_manifests(srcdir, verbose=False, ignore_errors=False, full_paths=False):
    """ find all paths containing a package file """
    paths = all_json_files(srcdir)
    manifests = []
    for path in paths:
        if is_manifest(path, verbose=verbose, raise_on_bad_json=not ignore_errors):
            if full_paths:
                manifests.append(path)
            else:
                manifests.append(split_path(path)[1])
    return sorted(manifests)


def all_remote_functions(region="us-east-1"):
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
