import os
import glob
import json
import re
from subprocess import check_output, CalledProcessError
from blambda.utils.base import pGreen, pRed, pBlue, pYellow, spawn
import time
from pprint import pprint

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
    (ret,stdout,stderr) = spawn("git rev-parse --show-toplevel")
    root = stdout[0] if ret == 0 else os.getcwd()
    jsonfiles = all_json_files(root)
    def ensure_json(pkgname):
        return pkgname if pkgname.endswith(".json") else "{}.json".format(pkgname)
    def match(pkg, jsonfile):
        return jsonfile.endswith(ensure_json(pkg)) and is_manifest(jsonfile, verbose)
    return {p:j for p in pkgnames for j in jsonfiles if match(p,j)}

def get_runtime(fname):
    manifest_file = find_manifest(fname)
    
def is_manifest(path, verbose=True):
    try:
        #hacky exclusions of files over 10k
        if os.path.getsize(path) < 10000:
            with open(path) as f:
                return json.load(f).get('blambda') == "manifest"
    except Exception as e:
        if verbose:
            print(pYellow("Failed to check manifest for file {}\n\tREASON: {}".format(path, e)))
    return False

def all_manifests(srcdir):
    """ find all paths containing a package file """
    paths = all_json_files(srcdir)
    manifests = []
    for path in paths:
        if is_manifest(path):
            manifests.append(split_path(path)[1])
    return sorted(manifests)

def all_remote_functions(region="us-east-1"):
    lmb = boto3.client('lambda', region_name=region)
    functions = {}
    def getfs(marker=None):
        lf = lmb.list_functions
        response = lf(Marker=marker) if marker else lf()
        functions.update({ f['FunctionName']: f['Description'] for f in response['Functions'] })
        if 'NextMarker' in response:
            getfs(response['NextMarker'])
    getfs()
    return functions

