#!/usr/bin/env python
import argparse
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from distutils.version import LooseVersion
from subprocess import check_output

import os
import requests
from termcolor import cprint

from .utils.findfunc import find_manifest, all_manifests, get_runtime

rsha = re.compile("([a-z0-9]{40})\s+HEAD.*")


def get_git_version(giturl):
    shas = check_output(['git', 'ls-remote', giturl[4:]])
    return rsha.match(shas).groups()[0]


def get_pip_version(package_name):
    url = "https://pypi.python.org/pypi/{}/json".format(package_name)
    data = requests.get(url).json()
    return sorted(list(data["releases"].keys()), key=LooseVersion, reverse=True)[0]


def get_py_version(dep):
    try:
        if dep.startswith("git+"):
            version = get_git_version(dep)
        else:
            version = get_pip_version(dep)
        return dep, version
    except Exception as e:
        cprint("{}: {}".format(dep, str(e)), 'red')
        return "error", str(e)


def get_node_version(module):
    try:
        version = check_output(['npm', 'view', module, 'version']).strip()
        print("{}: {}".format(module, version))
        return module, version
    except Exception as e:
        cprint("{}: {}".format(module, str(e)), 'red')
        return "error", str(e)


def get_block(data, open_delim="{", close_delim="}", start_pos=0):
    start = data.find(open_delim, start_pos)
    end = data.find(close_delim, start) + 1
    nested = data[start + 1:end].count(open_delim)
    for i in range(nested):
        end = data.find(close_delim, end) + 1
    return start, end


def dep_update(name, get_version, deps, overrides, only):
    # filter out 'skip' and overrides
    deps_to_check = {d: v for (d, v) in deps.items() if not (v == "skip" or d in overrides)}
    # reduce further if there is a whitelist
    if only:
        deps_to_check = {d: v for (d, v) in deps_to_check.items() if any(o in d for o in only)}

    with ThreadPoolExecutor(max_workers=32) as tpx:
        updated = {d: v for d, v in tpx.map(get_version, deps_to_check) if d != 'error'}

    updates = (set(updated.values()) - set(deps.values()))
    if updates:
        cprint("updated {} in {}".format(', '.join([os.path.basename(k) for k, v in updated.items() if v in updates]),
                                         name),
               'blue')
    deps.update(updated)
    # now sub in the overrides (but only the ones that we had)
    deps.update({d: v for d, v in overrides.items() if d in deps})
    return deps


def process_manifest(manifest, overrides, only):
    with open(manifest) as f:
        data = json.load(f)
    runtime = data.get('options', {}).get('Runtime', "")
    if "node" in runtime:
        get_version = get_node_version
    elif "python" in runtime:
        get_version = get_py_version
    else:
        cprint("unable to determine runtime language f or {}\n"
               "Make sure the manifest contains options/Runtime".format(manifest),
               'red')
        return

    # update the deps in place
    dep_update(os.path.basename(manifest), get_version, data['dependencies'], overrides, only)

    shutil.copy(manifest, "{}.bak".format(manifest))
    with open(manifest, "w") as f:
        json.dump(data, f, indent=4, sort_keys=True, separators=(',', ': '))

    template_manifest = "{}.tt2".format(manifest)
    if os.path.isfile(template_manifest):
        cprint("replacing deps in tt2 " + os.path.basename(template_manifest), 'info')
        with open(template_manifest) as f:
            tt2data = f.read()
        start = tt2data.find("dependencies")
        (start, end) = get_block(tt2data, start_pos=start)
        tt2deps = json.loads(tt2data[start:end])
        newdeps = dep_update(os.path.basename(template_manifest), get_version, tt2deps, overrides, only)
        dep_json = json.dumps(newdeps, indent=8, sort_keys=True, separators=(',', ': '))
        tt2data = tt2data[:start] + dep_json + tt2data[end:]
        shutil.copy(template_manifest, "{}.bak".format(template_manifest))
        with open(template_manifest, "w") as f:
            f.write(tt2data)


def update_function(fname, overrides, only, search=False):
    try:
        manifest = find_manifest(fname) if search else fname
        if manifest:
            process_manifest(manifest, overrides, only)
        else:
            cprint(fname + " not found", 'red')
    except Exception as e:
        print(e)


def main(args=None):
    parser = argparse.ArgumentParser("update the versions for the specified lambda functions")
    parser.add_argument('function_names', nargs='*', type=str, help='the base names of the lambda functions')
    parser.add_argument('--allpy', action='store_true', help='update all python functions')
    parser.add_argument('--allnode', action='store_true', help='update all node functions')
    parser.add_argument('--only', nargs='+', type=str, help='only update these deps')
    parser.add_argument('--file', type=str, help='filename containing lambda function names')
    parser.add_argument('--override', type=str,
                        help='filename of a json file containing the dependency section of '
                             'a manifest to use instead of the latest versions')

    args = parser.parse_args(args)

    search = True
    if args.allpy or args.allnode:
        term = "python" if args.allpy else "node"
        manifests = all_manifests(".", verbose=0, ignore_errors=True, full_paths=True)
        fnames = [name for name in manifests if term in get_runtime(name)]
        search = False
    elif args.file:
        with open(args.file) as f:
            fnames = [l.strip() for l in f.readlines()]
    else:
        fnames = args.function_names

    print("updating {} for {}".format(
        ', '.join(args.only) if args.only else 'all deps',
        ', '.join(fnames)
    ))

    overrides = {}
    if args.override:
        with open(args.override) as f:
            overrides = json.load(f)["dependencies"]

    fnames = set(fnames)
    with ThreadPoolExecutor(max_workers=32) as tpx:
        tpx.map(lambda fname: update_function(fname, overrides, args.only, search), fnames)
