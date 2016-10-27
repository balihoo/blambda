from __future__ import print_function
import sys
from subprocess import *
from contextlib import contextmanager
import time
import json

red = '\033[1;31m'
grn = '\033[1;32m'
yel = '\033[1;33m'
blu = '\033[1;34m'
mag = '\033[1;35m'
cyn = '\033[1;36m'
whi = '\033[0m'

def pRed(s):
	return "%s%s%s" % (red, s, whi)

def pGreen(s):
	return "%s%s%s" % (grn, s, whi)

def pCyan(s):
	return "%s%s%s" % (cyn, s, whi)

def pYellow(s):
	return "%s%s%s" % (yel, s, whi)

def pBlue(s):
	return "%s%s%s" % (blu, s, whi)

def pMagenta(s):
	return "%s%s%s" % (mag, s, whi)

def normalize(bytebuf):
    try:
        return bytebuf.decode("utf-8").strip().split('\n')
    except:
        return str(bytebuf)

def spawn(cmd, show = False, workingDirectory = None, raise_on_fail=False):
    if workingDirectory == "":
        workingDirectory = None
    p = Popen(cmd, cwd=workingDirectory, shell=True, stderr=PIPE, stdout=PIPE)
    (stdout, stderr) = (normalize(out) for out in p.communicate())

    if show:
        print("    ", pBlue(cmd), " ->", end=' ')
        if p.returncode == 0:
            print(pGreen(" [OK]"))
        else:
            print(pRed(" [FAIL]"))
            print("\n".join(stderr + stdout), file=sys.stderr)
    if raise_on_fail and p.returncode != 0:
        raise Exception("Spawning {} Failed:\n{}".format(cmd, "\n".join(stderr + stdout)))
    return (p.returncode, stdout, stderr)


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
    print("{}: {}s".format(tag, time.time()-t))

def json_filedump(name, obj):
    with open(name, 'w') as f:
        json.dump(obj, f, sort_keys=True, indent=2)

def json_fileload(name):
    with open(name) as f:
        return json.load(f)

