from __future__ import print_function

import json
import time
from contextlib import contextmanager
from subprocess import *

from termcolor import cprint


def normalize(bytebuf):
    try:
        return bytebuf.decode("utf-8").strip().split('\n')
    except:
        return str(bytebuf)


def spawn(cmd, show=False, working_directory=None, raise_on_fail=False):
    if working_directory == "":
        working_directory = None
    p = Popen(cmd, cwd=working_directory, shell=True, stderr=PIPE, stdout=PIPE)
    (stdout, stderr) = (normalize(out) for out in p.communicate())

    if show:
        if p.returncode == 0:
            cprint("   {} -> [OK]".format(cmd), 'blue')
        else:
            cprint("   {} -> [FAIL]\n{}".format(cmd, "\n".join(stderr + stdout)), 'red')
    if raise_on_fail and p.returncode != 0:
        cprint(cmd, 'red')
        cprint(stdout, 'red')
        cprint(stderr, 'red')
        raise Exception("Spawning {} Failed:\n{}".format(cmd, "\n".join(stderr + stdout)))
    return p.returncode, stdout, stderr


def humanize_time(secs):
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    ts = ''
    if hours:
        ts += "%dh" % hours
    if mins:
        ts += "%dm" % mins
    if secs:
        ts += "%ds" % secs
    return ts


@contextmanager
def timed(tag):
    t = time.time()
    yield
    cprint("{}: {}".format( tag, time.time() - t), 'red')


def json_filedump(name, obj):
    with open(name, 'w') as f:
        json.dump(obj, f, sort_keys=True, indent=2)


def json_fileload(name):
    with open(name) as f:
        return json.load(f)


def is_string(obj):
    """ is_string check -- python 2/3 compatible"""
    try:
        return isinstance(obj, basestring)
    except NameError:
        return isinstance(obj, str)
