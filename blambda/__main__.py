import argparse

#local imports
from . import (
    new,
    deploy,
    execute,
    setup_libs,
    update_versions,
    who_needs_update,
    config,
    cwlogs
)

def main():
    submap = {
        'new': new,
        'deploy': deploy,
        'exec': execute,
        'deps': setup_libs,
        'update-versions': update_versions,
        'stale': who_needs_update,
        'config': config,
        'logs': cwlogs,
    }

    parser = argparse.ArgumentParser(
        "Balihoo Command Line Tools for AWS Lambda function management",
        add_help=False
    )
    parser.add_argument('task', choices=submap.keys())
    args, sub_args = parser.parse_known_args()

    submap[args.task].main(sub_args)

if __name__ == "__main__":
    main()
