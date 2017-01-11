import os
import shutil
import re
from blambda.utils.base import pGreen, pRed, pBlue, spawn
from concurrent.futures import ThreadPoolExecutor

version_rex = re.compile("^[\w\.]+$")

def str_types():
    try:
        return (str, unicode)
    except NameError:
        return (str,)

def install_deps(dependencies, basedir, runtime, version_required=True, clean=False):
    """ installs node and python packages """
    if version_required:
        def valid_version(v):
            return type(v) in str_types() and version_rex.match(v)
        bad_Version = [dep for dep in dependencies if not valid_version(dependencies[dep])]
        if len(bad_Version) > 0:
            print(pRed("\nExact version required for: {}".format(", ".join(bad_Version))))
            print("  --> run 'update_versions' to set the latest version for all dependencies\n")
            return None
    deps_to_install = {d: v for (d,v) in dependencies.items() if not v == "skip"}

    install = None
    if "node" in runtime:
        # NPM has race condition problems when installing multiple versions of the same dep
        install_concurrency = 1
        moddir = os.path.join(basedir, "node_modules")
        if os.path.exists(moddir) and clean:
            shutil.rmtree(moddir)
        if not os.path.exists(moddir):
            os.mkdir(moddir)
        install = lambda args: npm_install(args[0], args[1], basedir)

    elif "python" in runtime:
        install_concurrency = 32
        libdir = os.path.join(basedir, "lib")
        if os.path.exists(libdir) and clean:
            shutil.rmtree(libdir)
        if not os.path.exists(libdir):
            os.mkdir(libdir)
        install = lambda args: pip_install(args[0], args[1], libdir)
    else:
        raise Exception("unable to determine package manager for {} ({})".format(basedir, runtime))

    with ThreadPoolExecutor(max_workers=install_concurrency) as tpx:
        results = list(tpx.map(install, deps_to_install.items()))
    return not any(results)

def npm_install(depname, version, cwd):
    """ installs a node package """
    command = " ".join(["npm", "install", "{}@{}".format(depname, version)])
    (r, s, e) = spawn(command, show=True, workingDirectory=cwd)
    return r

def pip_install(depname, version, target):
    """ installs a python package """
    install_cmd = ['install']

    local = depname.startswith('/home/')
    linked = version == "link"
    baligit = 'github.com/balihoo' in depname

    if baligit or local and not linked:
        # It's from one of our repos! Assume it's volatile and force an upgrade.
        install_cmd.append('--upgrade')
        if 'GITUSER' in os.environ and "https" in depname:
            print(pBlue("injecting credentials for {}".format(depname)))
            creds = "{}:{}@".format(os.environ['GITUSER'], os.environ['GITPASS'])
            depname = depname.replace("https://github", "https://{}github".format(creds))
    if local and linked:
        install_cmd += ['-e', depname]
    else:
        if version:
            if depname.startswith("git+"):
                depname += "@" + version
            else:
                depname += "==" + version
        install_cmd += [depname, '-t', target]
        print("\n" + pGreen(" ".join(install_cmd)))

    command = " ".join(["pip"] + install_cmd)
    (r, s, e) = spawn(command, show=True)
    return r
