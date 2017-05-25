import glob
import re

import os
from termcolor import colored

from .base import (
    spawn,
    timed,
    json_filedump,
    json_fileload
)
from .findfunc import find_manifests, all_remote_functions


def needs_update(manifest, sha_from, sha_to, show_diff=False, verbose=False):
    def vprint(msg):
        if verbose:
            print(msg)

    basename = os.path.splitext(os.path.basename(manifest))[0]
    files = json_fileload(manifest).get("source files", [])
    files = [f[0] if type(f) == list else f for f in files]
    files = [os.path.abspath(os.path.join(os.path.dirname(manifest), f)) for f in files]
    files = [glob.glob(f) for f in files]
    files = [f for fs in files for f in fs]

    # manifest won't be in the sources, but still instrumental
    files.append(manifest)
    # all of the sources are subject to being formed by tempfill.
    possible_tt2s = ['{}.tt2'.format(f) for f in files]
    files += [tt2 for tt2 in possible_tt2s if os.path.isfile(tt2)]
    (ret, stdout, stderr) = spawn("git diff {} {} --name-only".format(sha_from, sha_to))
    if ret != 0 and "unknown revision" in "".join(stdout + stderr):
        vprint(colored("{} needs update because SHA {} is unknown to git\n".format(basename, sha_from), 'red'))
        return True
    else:
        changed_files = [os.path.abspath(f) for f in stdout]
        matches = [cf for cf in changed_files for f in files if f == cf]
        if len(matches) > 0:
            names = ", ".join(os.path.basename(m) for m in matches)
            vprint(
                colored(basename, 'green') +
                colored(" needs update because {} has changed between {} and {}".format(names, sha_from, sha_to),
                        'yellow'))
            if show_diff:
                (ret, stdout, stderr) = spawn("git diff {}..{} {}".format(sha_from, sha_to, ' '.join(matches)))
                if ret == 0:
                    sep = '    ' if verbose else ''
                    print(sep + ('\n' + sep).join(stdout) + '\n\n')
            return True


def sha_from_desc(desc):
    dr = re.compile(".*\[SHA ([A-Za-z0-9]{7})[\]!].*")
    m = dr.match(desc)
    return m.groups()[0] if m else None


def potential_manifests(rfname):
    """ cuts a function name by underscore and creates
    a potential manifest paths
    """
    manifests = [rfname]
    # add all options of subdirs
    indices = [m.start() for m in re.finditer("_", rfname)]
    manifests += [rfname[:i] + '/' + rfname[i + 1:] for i in indices]
    return manifests


def potentials_from_remotes(env):
    """ gets the functions with shas from AWS """
    # filter for fulfillment_<fname>_<env>
    r = re.compile("fulfillment_([A-Za-z0-9_\-]+)_{}".format(env))
    potential_mfts = []
    shaless = []
    shafuncs = {}
    with timed("getting all functions from lambda"):
        remotes = all_remote_functions()
    print("got {} remote functions".format(len(remotes)))
    for remote in remotes:
        match = r.match(remote)
        if match:
            rfname = match.groups()[0]
            desc = remotes[remote]
            sha = sha_from_desc(desc)
            if sha:
                shafuncs[rfname] = sha
                potential_mfts += potential_manifests(rfname)
            else:
                shaless.append(rfname)
    return shafuncs, shaless, potential_mfts


def potentials_from_file(filename):
    """ you brought your own function names with shas """
    shafuncs = json_fileload(filename)
    potential_mfts = []
    for name in shafuncs:
        potential_mfts += potential_manifests(name)
    return shafuncs, [], potential_mfts


def who_needs_update(root, env="", from_sha_file=None, to_sha_file=None, show_diffs=False, verbose=True):
    def vprint(msg):
        if verbose:
            print(msg)

    vprint("finding matching manifests")
    if from_sha_file:
        (fromshas, noshas, potentials) = potentials_from_file(from_sha_file)
    else:
        (fromshas, noshas, potentials) = potentials_from_remotes(env)
        json_filedump("{}_shaless.json".format(env), noshas)
        json_filedump("{}_shas.json".format(env), fromshas)
        vprint("{} functions without a sha".format(len(noshas)))

    toshas = json_fileload(to_sha_file) if to_sha_file else {}

    vprint("{} potential manifests".format(len(potentials)))
    manifests = find_manifests(potentials, verbose=False)
    vprint("{} actual manifests".format(len(manifests)))

    def _needs_update(manifest, name):
        key = name.replace("/", "_")
        fromsha = fromshas[key]
        tosha = toshas.get(key, 'HEAD')
        return needs_update(manifest, fromsha, tosha, show_diffs, verbose)

    outdated = [name for (name, manifest) in manifests.items() if _needs_update(manifest, name)]
    return outdated + list(find_manifests(noshas).keys())
