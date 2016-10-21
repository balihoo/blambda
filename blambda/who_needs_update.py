#!/usr/bin/env python
import argparse
import os
from .utils.findfunc import who_needs_update

if __name__ == '__main__':
    parser = argparse.ArgumentParser("list functions that need updating")
    parser.add_argument('--file', type=str, help='filename to write output to')
    parser.add_argument('--env', type=str, help='dev or stage or something', default="dev")
    parser.add_argument('--prefix', type=str, help='prefix for your functions', default="")
    parser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
    args = parser.parse_args()

    this_dir = os.path.dirname(os.path.abspath(__file__))
    funcs = who_needs_update(this_dir, args.env, args.verbose)
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
