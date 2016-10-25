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
)

def main():
    submap = {
        'new': new,
        'deploy': deploy,
        'exec': execute,
        'execute': execute,
        'deps': setup_libs,
        'setup_libs': setup_libs,
        'update_versions': update_versions,
        'update-versions': update_versions,
        'who_needs_update': who_needs_update,
        'who-needs-update': who_needs_update,
        'stale': who_needs_update,
        'config': config,
    }

    parser = argparse.ArgumentParser("Balihoo Command Line Tools for AWS Lambda function management")
    parser.add_argument('task', choices=submap.keys())
    args, sub_args = parser.parse_known_args()

    submap[args.task].main(sub_args)

if __name__ == "__main__":
    main()
