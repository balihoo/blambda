import glob
import json
import re
import shutil

import os
from termcolor import cprint

from . import env_manager
from .base import spawn, is_string
from .findfunc import split_path


class LambdaManifest(object):
    def __init__(self, manifest_filename):
        super(LambdaManifest, self).__init__()

        with open(manifest_filename) as f:
            self.manifest = json.load(f)

        (self.basedir, self.function_name, _) = split_path(manifest_filename)
        self.lib_dir = os.path.join(self.basedir, "lib_{}".format(self.function_name.split('/')[-1]))
        self.runtime = self.manifest.get('options', {}).get('Runtime', 'python2.7').lower()

    def process_manifest(self, clean=False, prod=False):
        """ loads a manifest file, executes pre and post hooks and installs dependencies

        Args:
          clean (bool): whether or not to clean out the dependencies dir
          prod (bool): if true, do not install development dependencies
        """

        manifest = self.manifest
        basedir = self.basedir

        for command in manifest.get('before setup', []):
            spawn(command, show=True, working_directory=basedir, raise_on_fail=True)

        dependencies = manifest.get('dependencies', {})
        if not prod:
            dev_deps = manifest.get('dev dependencies', {})
            dependencies = merge_dependencies(dependencies, dev_deps)

        validate_dependencies(dependencies)
        deps_to_install = {d: v for (d, v) in dependencies.items() if not v == "skip"}

        if 'python' in self.runtime:
            env = env_manager.EnvManager(self.runtime)
            env.create(clean)
            if clean and os.path.exists(self.lib_dir):
                cprint("clean install -- removing " + self.lib_dir, 'yellow')
                shutil.rmtree(self.lib_dir)
            env.install_dependencies(self.lib_dir, **deps_to_install)

        elif 'node' in self.runtime:
            moddir = os.path.join(basedir, "node_modules")
            if os.path.exists(moddir) and clean:
                shutil.rmtree(moddir)
            if not os.path.exists(moddir):
                os.mkdir(moddir)

            # install node dependencies 1 at a time to avoid race condition issues
            for dependency, version in deps_to_install.items():
                spawn("npm install {}@{}".format(dependency, version), show=True, working_directory=basedir)
        else:
            raise RuntimeError("Unknown runtime: " + self.runtime)

        cprint("All dependencies installed", 'blue')

        for source in manifest['source files']:
            # check for files that are to be moved and link them
            if type(source) in (tuple, list):
                (src, dst) = source
                src = os.path.abspath(os.path.join(basedir, src))
                (dest_dir, _) = os.path.split(dst)
                dst = os.path.abspath(os.path.join(basedir, dst))
                if dest_dir:
                    dest_dir = os.path.abspath(os.path.join(basedir, dest_dir))
                    try:
                        os.makedirs(dest_dir)
                    except OSError:
                        pass
                # wildcards are allowed
                files = glob.glob(src)
                if len(files) == 0:
                    cprint("no glob for " + src, 'blue')
                for srcf in files:
                    srcf = os.path.abspath(srcf)
                    dstf = dst if len(files) == 1 else os.path.join(dest_dir, os.path.basename(srcf))
                    if not os.path.exists(dstf):
                        spawn(
                            "ln -s {} {}".format(srcf, dstf),
                            show=True,
                            working_directory=basedir,
                            raise_on_fail=True
                        )
                    else:
                        cprint("Not (re)linking {} to {}, destination exists".format(srcf, dstf), 'blue')

        for command in manifest.get('after setup', []):
            spawn(command, show=True, working_directory=basedir, raise_on_fail=True)


def merge_dependencies(deps, dev_deps):
    """ checks for each possible dependency section within the manifest and merges
    them into a single dictionary, throwing if different versions of the same package are specified
    Args:
      deps (dict): the release dependencies
      dev_deps (dict): the development dependencies
    Returns:
      dict: validated merged dependencies
    """
    # cross correlate the packages and extract mismatching versions
    conflicts = [k for k in deps for d in dev_deps if k == d and deps[k] != dev_deps[d]]
    if conflicts:
        for package in conflicts:
            cprint(
                "Multiple versions of package {} specified: {} and {}".format(
                    package,
                    deps[package],
                    dev_deps[package]),
                'red')
        raise Exception("Failed to install dependencies: version mismatch")

    # return a new dict containing all dependencies
    merged_dependencies = dict(deps)
    merged_dependencies.update(dev_deps)
    return merged_dependencies


def validate_dependencies(dependencies):
    version_rex = re.compile("^[\w\.]+$")
    bad_version = [dep for dep, version in dependencies.items()
                   if not (is_string(version) and version_rex.match(version))]

    if len(bad_version) > 0:
        cprint("\nExact version required for: {}\n  --> run 'update_versions' "
               "to set the latest version for all dependencies\n".format(", ".join(bad_version)),
               'red')
        raise Exception('Failed to install dependencies')
