import os
import glob
import json
import re
from subprocess import check_output, CalledProcessError
from blambda.utils.base import pGreen, pRed, pBlue, pYellow, spawn
import time

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

def who_needs_update(root, env="dev", verbose=True):
    start = time.time()
    def vprint(msg):
        if verbose:
            print("{:.3f}] {}".format(time.time() - start, msg))

    def needs_update(manifest, sha):
        basename = os.path.splitext(os.path.basename(manifest))[0]
        files = []
        with open(manifest) as f:
            files = json.load(f).get("source files", [])
        files = [f[0] if type(f) == list else f for f in files]
        files = [os.path.abspath(os.path.join(os.path.dirname(manifest), f)) for f in files]
        #manifest won't be in the sources, but still instrumental
        files.append(manifest)
        #all of the sources are subject to being formed by tempfill.
        possible_tt2s = ['{}.tt2'.format(f) for f in files]
        files += [tt2 for tt2 in possible_tt2s if os.path.isfile(tt2)]
        (ret,stdout,stderr) = spawn("git diff {} HEAD --name-only".format(sha))
        if ret != 0 and "unknown revision" in "".join(stdout + stderr):
            vprint("{} needs update because SHA {} is unknown to git".format(basename, sha))
            return True
        else:
            changed_files = [os.path.abspath(f) for f in stdout]
            matches = [cf for cf in changed_files for f in files if f == cf]
            if len(matches) > 0:
                names = ", ".join(os.path.basename(m) for m in matches)
                vprint("{} needs update because {} has changed since {}".format(basename, names, sha))
                return True

    vprint("getting all functions from lambda")
    remotes = all_remote_functions()
    vprint("got {} remote functions".format(len(remotes)))

    releases = {}
    #filter for fulfillment_<fname>_dev
    r = re.compile("fulfillment_([A-Za-z0-9_]+)_{}".format(env))
    dr = re.compile(".*\[SHA ([A-Za-z0-9]{7})[\]!].*")
    def sha_from_desc(dsc):
        m = dr.match(desc)
        return m.groups()[0] if m else None

    noshas = []
    shas = {}
    potential_manifests = []
    vprint("finding matching manifests")
    for remote in remotes:
        match = r.match(remote)
        if match:
            rfname = match.groups()[0]
            desc = remotes[remote]
            sha = sha_from_desc(desc)
            if sha:
                shas[rfname] = sha
                #add the name as is
                potential_manifests.append(rfname)
                #add all options of subdirs
                indices = [m.start() for m in re.finditer("_", rfname)]
                potential_manifests += [rfname[:i] + '/' + rfname[i+1:] for i in indices]
            else:
                noshas.append(rfname)

    vprint("{} functions without a sha".format(len(noshas)))
    vprint("{} potential manifests".format(len(potential_manifests)))
    manifests = find_manifests(potential_manifests, verbose=False)
    vprint("{} actual manifests".format(len(manifests)))

    outdated =  [name for (name, manifest) in manifests.items() if needs_update(manifest, shas[name.replace("/", "_")])]
    return outdated + find_manifests(noshas).keys()

