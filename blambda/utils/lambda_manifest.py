import glob
import json
import re
import shutil

import os

from pathlib import Path
from termcolor import cprint

from . import env_manager
from .base import spawn, is_string


def lazy_property(func):
    attr = '__lazy_property' + func.__name__

    @property
    def _lazy_property(self):
        if not hasattr(self, attr):
            setattr(self, attr, func(self))
        return getattr(self, attr)

    return _lazy_property


class LambdaManifest(object):
    MAX_FILESIZE = 10000

    def __init__(self, manifest_filename):
        super(LambdaManifest, self).__init__()
        self.path = Path(manifest_filename).absolute()
        self.manifest = self.load_and_validate(manifest_filename)

    def __repr__(self):
        return f"<LambdaManifest({self.full_name})>"

    def __hash__(self):
        return self.full_name

    def load_and_validate(self, manifest_filename):
        if os.path.getsize(manifest_filename) > self.MAX_FILESIZE:
            raise ValueError(f'Manifest too large: "{manifest_filename}"')

        with open(manifest_filename) as f:
            manifest = json.load(f)

        if type(manifest) != dict or manifest.get('blambda') != "manifest":
            raise ValueError(f'Manifest not valid: "{manifest_filename}"')

        return manifest

    @lazy_property
    def basedir(self):
        return self.path.parent

    @lazy_property
    def group(self):
        return self.path.parent.stem

    @lazy_property
    def short_name(self):
        return self.path.stem

    @lazy_property
    def full_name(self):
        """ Function name (e.g. 'timezone' or 'adwords/textad')

        If the function name doesn't match it's parent folder, let's include the folder name
        as part of the function name.. so timezone/timezone -> timezone, but adwords/textad -> adwords/textad

        Returns:
            str: collapsed function/group name
        """
        func = self.path.stem
        if self.group in func:
            return func
        return self.group + '/' + func

    @lazy_property
    def lib_dir(self):
        return self.basedir / ('lib_' + self.short_name)

    @lazy_property
    def runtime(self):
        return self.manifest.get('options', {}).get('Runtime', 'python2.7').lower()

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
