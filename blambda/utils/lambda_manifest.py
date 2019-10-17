import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from termcolor import cprint

from . import env_manager
from .base import spawn, is_string


def lazy_property(func):
    """ Properties decorated with this will be lazy evaluated and stored.

    This is used so that we don't end up recalculating a bunch of path logic unnecessarily.

    """
    attr = '__lazy_property' + func.__name__

    @property
    def _lazy_property(self):
        if not hasattr(self, attr):
            setattr(self, attr, func(self))
        return getattr(self, attr)

    return _lazy_property


class LambdaManifest(object):
    """ LambdaManifest reads the manifest.json / directory structure to handle lambda function metadata

    Figures out the lambda function name / group based on the directory structure
    Validates / parses the manifest .json file to get dependencies / runtime / source files / etc...

    """
    MAX_FILESIZE = 10000

    def __init__(self, manifest_filename, parse_json=False):
        super(LambdaManifest, self).__init__()
        self.path = Path(manifest_filename).absolute()
        if parse_json:
            # noinspection PyStatementEffect
            self.json  # todo: this loads/validates as a side effect, eew

    def __repr__(self):
        return f"<LambdaManifest({self.full_name})>"

    def __hash__(self):
        return self.full_name

    @lazy_property
    def json(self):
        return self.load_and_validate(self.path)

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
        group = self.group
        if func.startswith(group):
            return func
        return group + '/' + func

    @lazy_property
    def lib_dir(self):
        return self.basedir / ('lib_' + self.short_name)

    @lazy_property
    def node_dir(self):
        return self.basedir / ('node_modules_' + self.short_name)

    @lazy_property
    def deployed_name(self):
        return self.full_name.replace('/', '_')

    @lazy_property
    def runtime(self):
        return self.json.get('options', {}).get('Runtime', 'python2.7').lower()

    def source_files(self, dest_dir: Path = None):
        """ Return a generator yielding tuples of (source_file, destination_target), unraveling any globs along the way

        There are 3 cases for the "source files" section of the manifest:

            straight copy:
                "handler.coffee",

            2 argument copy:
                ["../shared/lambda_chain.py", "lambda_chain.py"],

            2 argument glob:
                ["../../../shared/*.coffee", "./*.coffee"],

        However, .coffee files are a special case, when deploying, they are prefixed with the lambda function name
        in the deployment zip
        """
        if dest_dir is None:
            dest_dir = self.basedir
        else:
            dest_dir = Path(dest_dir)

        for source_spec in self.json.get('source files', []):
            if type(source_spec) in (tuple, list):
                (src_pattern, dst_pattern) = source_spec

                if '*' in str(src_pattern):
                    src_paths = self.basedir.glob(src_pattern)
                else:
                    src_paths = [self.basedir / src_pattern]

                for src in src_paths:
                    src = (self.basedir / src).resolve()
                    dst = dest_dir / dst_pattern

                    if '*' in dst.name:
                        dst = dst.parent / src.name

                    yield src, dst
            else:
                if dest_dir != self.basedir:
                    src = (self.basedir / source_spec).resolve()
                    if src.suffix == '.coffee' or src.suffix == '.js':
                        yield src, dest_dir / self.short_name / source_spec
                    else:
                        yield src, dest_dir / source_spec

    def process_manifest(self, clean=False, prod=False):
        """ loads a manifest file, executes pre and post hooks and installs dependencies

        Args:
          clean (bool): whether or not to clean out the dependencies dir
          prod (bool): if true, do not install development dependencies
        """
        # todo: does this logic belong here? the answer is no.
        manifest = self.json

        for command in manifest.get('before setup', []):
            spawn(command, show=True, working_directory=self.basedir, raise_on_fail=True)

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
            # currently there's no way to npm install to a directory other than <whatever>/node_modules
            # this installs to a tempdir, where the node_modules of that tempdir is symlinked to the dir we want

            tempdir = tempfile.mkdtemp()
            node_modules = Path(tempdir) / "node_modules"
            node_modules.symlink_to(self.node_dir)

            if clean and self.node_dir.exists():
                shutil.rmtree(self.node_dir)

            self.node_dir.mkdir(exist_ok=True)

            # install node dependencies 1 at a time to avoid race condition issues
            for dependency, version in deps_to_install.items():
                spawn(f"npm install {dependency}@{version}", show=True, working_directory=tempdir)

            shutil.rmtree(tempdir)

        else:
            raise RuntimeError("Unknown runtime: " + self.runtime)

        cprint("All dependencies installed", 'blue')

        # check for files that are to be moved and link them
        for src, dst in self.source_files():
            dst.parent.mkdir(parents=True, exist_ok=True)

            if not dst.exists():
                dst.symlink_to(src)
            elif dst.is_symlink():
                cprint(f"Not (re)linking {src} to {dst}, destination exists", 'blue')
            else:
                cprint(f"Can't symlink: {dst} exists, but is not a symlink", 'red')

        for command in manifest.get('after setup', []):
            spawn(command, show=True, working_directory=self.basedir, raise_on_fail=True)


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
