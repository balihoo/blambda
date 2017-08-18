""" Check which deployed lambda functions are out of date compared to HEAD """
import functools
import os
import re

from .base import (
    spawn,
    timed,
    json_filedump
)
from .findfunc import find_manifests, all_remote_functions, get_search_root


def who_needs_update(env="", show_diffs=False, verbose=True):
    """ Check AWS for stale lambda functions

    Gets the deployed SHA for each lambda function, then compares HEAD to that SHA to check for differences.

    Args:
        env (str): dev/stage/prod
        show_diffs (bool): run 'git diff' as well
        verbose (bool): show some debug info

    Returns:
        dict: all functions needing update, debug info if verbose=True
    """
    info = {}

    deployed_shas, missing_shas, potentials, remote_functions = potentials_from_remotes(env)
    json_filedump(f"{env}_shaless.json", missing_shas)
    json_filedump(f"{env}_shas.json", deployed_shas)

    manifests = find_manifests(potentials)

    if verbose:
        info['debug'] = {
            'functions_missing_sha': len(missing_shas),
            'potential_manifests': len(potentials),
            'actual_manifests': len(manifests),
            'remote_functions': len(remote_functions)
        }

    outdated = [
        status for status in (
            check_update_status(m, deployed_shas[m.deployed_name], show_diffs)
            for m in manifests
        ) if status
    ]

    no_sha_found = [
        {'function': m.full_name,
         'reason': 'no sha found on deployed function'}
        for m in find_manifests(missing_shas)
    ]

    info['functions_needing_update'] = outdated + no_sha_found

    return info


def check_update_status(manifest, deployed_sha, show_diff=False):
    """ Check to see if a given lambda function has changed between the deployed SHA and HEAD.

    Args:
        manifest (LambdaManifest): the lambda function
        deployed_sha (str): the git SHA of the lambda function deployed on AWS
        show_diff (bool): if True, run 'git diff'

    Returns:
        dict: contains the function name / reason it needs updating / diff. If empty, no change is needed.
    """
    local_sha = 'HEAD'

    out = {}
    (ret, changed_files, stderr) = git_changed_filenames(deployed_sha, local_sha, _lambda_source_files(manifest))
    if ret != 0 and "unknown revision" in changed_files + stderr:
        out['function'] = manifest.full_name
        out['reason'] = f"SHA {deployed_sha} is unknown to git"
    elif changed_files:
        out['function'] = manifest.full_name
        out['reason'] = f"between {deployed_sha} and {local_sha} the following files have changed: " \
                        f"{', '.join(os.path.basename(f) for f in changed_files)}"
        if show_diff:
            (ret, diff, stderr) = git_diff(deployed_sha, local_sha, changed_files)
            if ret == 0:
                out['diff'] = diff

    return out


def sha_from_desc(desc):
    """ Extract the git SHA embedded in the description field """
    m = re.match(".*\[SHA ([A-Za-z0-9]{7})[\]!].*", desc)
    if m:
        return m.groups()[0]


def guess_potential_manifests(function_name):
    """ Attempts to guess where to find the code for a given function based on the name in AWS

    The function names are delimited with '_' in AWS, so we have to guess where the '/' would be, if there is one.

    Args:
        function_name(str): function name e.g. 'appnexus_pause_creatives'

    Returns:
        List[str]: All valid names: ['appnexus_pause_creatives', 'appnexus/pause_creatives', 'appnexus_pause/creatives']
    """
    manifests = [function_name]
    indices = [m.start() for m in re.finditer("_", function_name)]
    manifests += [function_name[:i] + '/' + function_name[i + 1:] for i in indices]
    return manifests


def potentials_from_remotes(env):
    """ get information on lambda functions deployed in AWS

    By convention, the git SHA is automatically stored in the description when deployed via blambda.  This queries
    AWS for a list of functions / descriptions (which should hopefully all have SHAs).
    """

    potential_manifests = []
    missing_shas = []
    deployed_shas = {}
    with timed("getting all functions from lambda"):
        remotes = all_remote_functions()
    print("got {} remote functions".format(len(remotes)))

    fulfillment_pattern = re.compile("fulfillment_([A-Za-z0-9_\-]+)_" + env)  # filter for fulfillment_<fname>_<env>
    for name, description in remotes.items():
        try:
            function_name = fulfillment_pattern.match(name).groups()[0]
        except AttributeError:
            # skip any lambda functions that don't match the regex
            pass
        else:
            sha = sha_from_desc(description)
            if sha:
                deployed_shas[function_name] = sha
                potential_manifests += guess_potential_manifests(function_name)
            else:
                missing_shas.append(function_name)

    return deployed_shas, missing_shas, potential_manifests, remotes


@functools.lru_cache()
def get_git_root():
    # cached because in the context of these functions we're not changing dirs, so we only need to run this once
    return get_search_root()


def git_changed_filenames(sha1, sha2, files):
    """ See if any of the files changed between sha1 and sha2 """
    return_value, stdout, stderr = spawn(f"git diff {sha1} {sha2} --name-only {' '.join(files)}")
    stdout = [line for line in stdout if line]  # filter out blank lines
    return return_value, stdout, stderr


def git_diff(sha1, sha2, files):
    """ Return the actual diff of files between sha1 and sha2 """

    root = get_git_root()
    files = [os.path.join(root, f) for f in files]
    return spawn(f"git diff {sha1}..{sha2} {' '.join(files)}")


def _lambda_source_files(manifest):
    """ Get a list of the manifest / source files / possible .tt2 files relevant to a given lambda function

    Args:
        manifest (LambdaManifest): the lambda function object

    Returns:
        List[str]: List of all possible files that could be relevant to git for this lambda function

    """
    files = [str(manifest.path)]
    for source_file in manifest.json.get("source files", []):
        if type(source_file) == list:
            source_file = source_file[0]
        source_file = str(manifest.basedir / source_file)
        files.append(source_file)
        tt2_file = source_file + '.tt2'

        # all of the sources are subject to being formed by tempfill.
        if os.path.exists(tt2_file):
            files.append(tt2_file)
    return files
