import argparse

# local imports
from . import (
    new,
    show,
    deploy,
    execute,
    setup_libs,
    update_versions,
    who_needs_update,
    config,
    cwlogs,
    local_execute,
    local_test
)


def main():
    available_subparsers = {
        'new': new,
        'deploy': deploy,
        'exec': execute,
        'deps': setup_libs,
        'update': update_versions,
        'stale': who_needs_update,
        'config': config,
        'logs': cwlogs,
        'show': show,
        'local': local_execute,
        'test': local_test,
    }

    parser = argparse.ArgumentParser("Balihoo Command Line Tools for AWS Lambda function management")
    parser.add_argument('--version', action='store_true', help='echo version number and exit')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='verbose output')
    subparsers = parser.add_subparsers(dest='cmd')

    for subparser_name, submodule in available_subparsers.items():
        subparser = subparsers.add_parser(subparser_name,
                                          help=submodule.__doc__,
                                          description=submodule.__doc__)
        submodule.setup_parser(subparser)

    args = parser.parse_args()

    if args.version:
        import pkg_resources
        print(f"blambda {pkg_resources.require('blambda')[0].version}")
    else:
        if args.cmd is None:
            parser.print_help()
        else:
            available_subparsers[args.cmd].run(args)


if __name__ == "__main__":
    main()
