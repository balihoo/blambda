import argparse
import deploy
import execute
import setup_libs

def main():
    submap = {
        'deploy': deploy,
        'exec': execute,
        'execute': execute,
        'deps': setup_libs,
        'setup_libs': setup_libs
    }

    parser = argparse.ArgumentParser("Balihoo Command Line Tools for AWS Lambda function management")
    parser.add_argument('task', choices=submap.keys())
    args, sub_args = parser.parse_known_args()

    submap[args.task].main(sub_args)

if __name__ == "__main__":
    main()
