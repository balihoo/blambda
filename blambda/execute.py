import argparse
import json
import sys

import boto3
from botocore.client import Config as BotoConfig

from . import config

cfg = config.load()


def main(args=None):
    parser = argparse.ArgumentParser("execute python lambda functions")
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--payload', type=str, help='the payload function', default=None)
    parser.add_argument('--prefix', type=str, help='the prefix for the function', default=cfg.get('application'))
    parser.add_argument('--env', type=str, help='the environment this function will run in', default=cfg.get('environment'))
    args = parser.parse_args(args)

    payload = args.payload
    if payload is None:
        print("reading payload from stdin")
        payload = sys.stdin.read()

    function_name = args.function_name
    if args.prefix:
        function_name = "{}_{}".format(args.prefix, function_name)
    if args.env:
        function_name = "{}_{}".format(function_name, args.env)

    client = boto3.client(
        'lambda',
        region_name='us-east-1',
        config=BotoConfig(
            connect_timeout=10,
            read_timeout=300)
    )

    response = client.invoke(
        FunctionName=function_name,
        Payload=payload.encode('utf-8')
    )
    if response['StatusCode'] == 200:
        try:
            payload = json.loads(response['Payload'].read())
            print(json.dumps(payload, indent=4))
        except:
            print(response)
    else:
        print(response)


if __name__ == '__main__':
    main()
