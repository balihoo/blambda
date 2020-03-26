""" env_manager.py

Uses pyenv and pyenv-virtualenv to programmatically manage python environments.
"""

import subprocess as sp
from collections import namedtuple
import concurrent.futures

import os
import sys

from termcolor import cprint

LambdaRuntime = namedtuple('LambdaRuntime', ('name', 'version', 'env_name'))
py27 = LambdaRuntime('python2.7', '2.7.13', 'blambda-2.7')
py36 = LambdaRuntime('python3.6', '3.6.1', 'blambda-3.6')
py37 = LambdaRuntime('python3.7', '3.7.5', 'blambda-3.7')
py38 = LambdaRuntime('python3.8', '3.8.1', 'blambda-3.8')

runtimes = {
    py27.name: py27,
    py36.name: py36,
    py37.name: py37,
    py38.name: py38
}

DEFAULT_RUNTIME = py36

class EnvManager(object):
    def __init__(self, runtime):
        super(EnvManager, self).__init__()
        self.runtime = runtimes.get(runtime.lower(), DEFAULT_RUNTIME)

    @property
    def pyenv(self):
        root = os.environ.get('PYENV_ROOT', os.path.expanduser('~/.pyenv/'))
        return os.path.join(root, 'versions', self.runtime.env_name)

    @property
    def python(self):
        return os.path.join(self.pyenv, 'bin/python')

    @property
    def pip(self):
        return os.path.join(self.pyenv, 'bin/pip')

    def create(self, clean=False):
        """ Create an environment for a particular lambda function

        Args:
            clean: if True, remove the lib_dir before continuing
        """
        self.install_python_interpreter()
        self.create_virtualenv(clean)

    def install_python_interpreter(self):
        """ Install the base python interpreter.  This needs to be created before the virtualenv can be created. """
        cprint("Checking for base python interpreter", "yellow")

        sp.check_call("pyenv install -s " + self.runtime.version, shell=True)

    def create_virtualenv(self, clean=True):
        """ Create a blambda virtualenv

        Args:
            clean: if True, remove the virtualenv before creating
        """

        if os.path.exists(self.pyenv):
            if not clean:
                cprint(self.runtime.env_name + " env exists, skipping...", "yellow")
                return

            cprint("Removing {} virtualenv for clean install...".format(self.runtime.env_name), "yellow")
            sp.check_call("pyenv uninstall -f " + self.runtime.env_name, shell=True)

        cprint("Creating {} virtualenv...".format(self.runtime.env_name), "yellow")

        args = ['pyenv', 'virtualenv', '--clear', self.runtime.version, self.runtime.env_name]
        sp.check_call(args)

    def install_dependencies(self, lib_dir, **dependencies):
        """ Install dependencies with pip

        Args:
            lib_dir: directory where the dependencies should be stored (this is separate from the virtualenv dir)
            **dependencies: dict of { 'dependency_name': 'dependency_version' }

        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as parallel:
            all_futures = {parallel.submit(self._install_dependency, dep, lib_dir, version): dep
                           for dep, version in dependencies.items()}  # key is the futures object, value is the dep

            for future in concurrent.futures.as_completed(all_futures):
                dep = all_futures[future]
                try:
                    future.result()
                except Exception as e:
                    cprint("{}: Unhandled exception when pip installing '{}'".format(dep, e), 'red')
                    sys.exit(1)
                else:
                    cprint('pip: finished installing ' + dep, 'blue')

    def _install_dependency(self, dep, lib_dir, version):
        install_cmd = ['install']
        local = dep.startswith('/home/')
        linked = version == "link"
        is_balihoo_repo = 'github.com/balihoo' in dep
        # Check if pip should force an upgrade
        if is_balihoo_repo or (local and not linked):
            # It's from one of our repos! Assume it's volatile and force an upgrade.
            install_cmd.append('--upgrade')
            if 'GITUSER' in os.environ and "https" in dep:
                creds = "{}:{}@".format(os.environ['GITUSER'], os.environ['GITPASS'])
                dep = dep.replace("https://github", "https://{}github".format(creds))
        if local and linked:
            # -e will install the package in dev/editable mode
            # there's an outstanding bug which prevents pip from using both -e and -t at the same time
            install_cmd.extend(('-e', dep))
        else:
            if version:
                if dep.startswith("git+"):
                    dep += "@" + version
                else:
                    dep += "==" + version
            install_cmd.extend([dep, '-t', lib_dir])

        # actually install the package using pip
        sp.check_call([self.pip] + install_cmd)
