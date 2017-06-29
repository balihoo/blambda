"""
List local functions
"""

import os

from .utils.findfunc import all_manifests


# don't delete, this is necessary for the argparsing logic
def setup_parser(parser):
    pass


def run(args):
    manifests = all_manifests(".", verbose=(args.verbose > 1), ignore_errors=True, full_paths=True)

    for m in manifests:
        dname = os.path.basename(os.path.dirname(m))
        fname = os.path.splitext(os.path.basename(m))[0]
        fname = fname if fname == dname else os.path.join(dname, fname)
        if args.verbose == 0:
            print(fname)
        else:
            print("{}: {}".format(fname, m))
