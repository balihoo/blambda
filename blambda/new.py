import boto3
from botocore.exceptions import ClientError
from botocore.client import Config as BotoConfig
import json
import argparse
import os
import subprocess
import sys

from .utils.findfunc import (
  find_manifest,
  split_path
)

from . import config

handler_code = {
    "python": '\n'.join([
        "def lambda_handler(event, context):",
        "    return event"
    ]),
    "coffee": '\n'.join([
        "exports.handler = (event, context) ->",
        "    event"
    ]),
}

def main(args=None):
    parser = argparse.ArgumentParser("create a new lambda function")
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--runtime', type=str, help='node or python', default='python')
    parser.add_argument('--nodir', help='do not create a directory', action='store_true')
    args = parser.parse_args(args)

    fname = args.function_name
    runtimes = {
        'python': ('python2.7', 'py'),
        'coffee': ('nodejs4.3', 'coffee')
    }
    runtime, ext = runtimes[args.runtime]
    filename = "{}.{}".format(fname, ext)
    manifest = {
        "blambda": "manifest",
        "dependencies": {},
        "options": {
            "Description": fname,
            "Timeout": 300,
            "Runtime": runtime
        },
        "permissions": [],
        "source files": [filename]
    }

    if args.nodir:
        handler_path = filename
        manifest_path = "{}.json".format(fname)
    else:
        if not os.path.exists(fname):
            os.makedirs(fname)
        handler_path = os.path.join(fname, filename)
        manifest_path = os.path.join(fname, "{}.json".format(fname))

    with open(handler_path, 'w') as f:
        f.write(handler_code[args.runtime])

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=4, sort_keys=True)
