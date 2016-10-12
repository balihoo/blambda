import argparse
import deploy
import execute
import setup_libs
import update_versions
import who_needs_update
import config

def main():
    submap = {
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
        'config': config
    }

    parser = argparse.ArgumentParser("Balihoo Command Line Tools for AWS Lambda function management")
    parser.add_argument('task', choices=submap.keys())
    args, sub_args = parser.parse_known_args()

    submap[args.task].main(sub_args)

if __name__ == "__main__":
    main()
