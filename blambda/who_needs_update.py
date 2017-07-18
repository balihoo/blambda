"""
list functions that need updating
"""
import json
import argparse

import sys

from termcolor import colored, cprint

from .utils.stale import who_needs_update


def _print_colorful_diff_line(line, output_stream):
    if line.startswith('-'):
        cprint(line, 'red', file=output_stream)
    elif line.startswith('+'):
        cprint(line, 'green', file=output_stream)
    elif line.startswith('@@'):
        idx = line.rfind('@@') + 2
        print(colored(line[:idx], 'cyan') + line[idx:], file=output_stream)
    else:
        print(line, file=output_stream)


def setup_parser(parser):
    formats = ('json', 'human')
    envs = ('dev', 'stage', 'prod')
    parser.add_argument('--file', type=argparse.FileType('w'), help='filename to write output to', default=sys.stdout)
    parser.add_argument('--env', choices=envs, default="dev", help="Which env (default: %(default)s)")
    parser.add_argument('--format', choices=formats, default='human', help="Output format (default: %(default)s)")
    parser.add_argument('--show-diffs', '--diffs', help='show the diff for each function', action='store_true')


def run(args):
    update = who_needs_update(
        args.env,
        show_diffs=args.show_diffs,
        verbose=args.verbose
    )
    if update:
        if args.format == 'json':
            print(json.dumps(update, indent=4), file=args.file)
        else:
            # print human-readable format
            if args.verbose:
                print(f"{update['debug']['remote_functions']} remote functions", file=args.file)
                print(f"{update['debug']['functions_missing_sha']} functions deployed without a sha", file=args.file)
                print(f"{update['debug']['potential_manifests']} potential manifests", file=args.file)
                print(f"{update['debug']['actual_manifests']} actual manifests", file=args.file)

            for item in update['functions_needing_update']:
                if args.verbose:
                    print(item['function'] + colored('  -- ' + item['reason'], 'blue'), file=args.file)
                else:
                    print(item['function'], file=args.file)

                diff = item.get('diff')
                if diff:
                    for line in diff:
                        _print_colorful_diff_line(line, args.file)
