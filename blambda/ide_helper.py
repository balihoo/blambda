"""
Insert a function's base / lib dirs into intellij's indexing path. This works by rewriting the project's
*.iml file, inserting the proper paths as source directories.
"""
import os
import re

from bs4 import BeautifulSoup

from .utils.findfunc import find_manifest
from .utils.lambda_manifest import LambdaManifest


def find_iml_file(project_dir):
    return [
        os.path.join(project_dir, f) for f in os.listdir(project_dir)
        if f.endswith('.iml')
    ][0]


def setup_parser(parser):
    parser.add_argument('function_name', type=str, help='the base name of the function')


def run(args):
    manifest_filename = find_manifest(args.function_name)
    manifest = LambdaManifest(manifest_filename)
    project_dir, *source_dirs = re.match(r'(.*)((/python/src/.*)/lib_.*)$', manifest.lib_dir).groups()

    iml_file = find_iml_file(project_dir)

    with open(iml_file) as f:
        data = BeautifulSoup(f, "lxml-xml")

    content = data.module.component.content
    content.clear()

    for source_dir in source_dirs:
        content.append(data.new_tag("sourceFolder", isTestSource="false", url="file://$MODULE_DIR$" + source_dir))

    with open(iml_file, 'w') as f:
        print(data.prettify(), file=f)
