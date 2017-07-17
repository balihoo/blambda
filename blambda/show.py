"""
List local functions
"""

from .utils.findfunc import find_all_manifests
from termcolor import colored


# don't delete, this is necessary for the argparsing logic
def setup_parser(parser):
    pass


def run(args):
    manifests = find_all_manifests(".", verbose=(args.verbose > 1))

    for m in manifests:
        if args.verbose >= 1:

            print(f'{m.path}: {colored(m.full_name, "red")}')
        else:
            print(m.full_name)
