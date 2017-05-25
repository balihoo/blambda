import argparse

import os

from .utils.diffs import who_needs_update


def main(args=None):
    parser = argparse.ArgumentParser("list functions that need updating")
    parser.add_argument('--file', type=str, help='filename to write output to')
    parser.add_argument('--env', type=str, help='dev or stage or something', default="dev")
    parser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
    parser.add_argument('--fromshas', type=str, help="list of functions with shas to check (default: gets from 'env')", default=None)
    parser.add_argument('--toshas', type=str, help='list of functions with shas to use as base (defaults to HEAD)', default=None)
    parser.add_argument('--diffs', help='show the diff for each function', action='store_true')

    args = parser.parse_args(args)

    this_dir = os.path.dirname(os.path.abspath(__file__))
    funcs = who_needs_update(
        this_dir,
        args.env,
        from_sha_file=args.fromshas,
        to_sha_file=args.toshas,
        show_diffs=args.diffs,
        verbose=args.verbose
    )
    if funcs:
        if args.file:
            with open(args.file, "w") as f:
                for func in funcs:
                    f.write("{}\n".format(func))
                    print(func)
        else:
            for func in funcs:
                print(func)
    elif args.verbose:
        print("zero functions need updating")
