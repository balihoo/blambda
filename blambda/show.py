import argparse
import os
from .utils.findfunc import all_manifests

def main(args=None):
    parser = argparse.ArgumentParser("list local functions")
    parser.add_argument('-v', '--verbose', help='verbose output', action='count', default=0)
    args = parser.parse_args(args)

    manifests = all_manifests(".", verbose=(args.verbose > 1), ignore_errors=True, full_paths=True)

    for m in manifests:
        fname = os.path.splitext(os.path.basename(m))[0]
        if args.verbose == 0:
            print(fname)
        else:
            print("{}: {}".format(fname, m))

