"""
Insert a function's base / lib dirs into intellij's indexing path. This works by rewriting the project's
*.iml file, inserting the proper paths as source directories.
"""
from pathlib import Path

from bs4 import BeautifulSoup

from .utils.findfunc import find_manifest
from .utils.lambda_manifest import LambdaManifest


def find_iml_file(path: Path) -> Path:
    if str(path) == path.anchor:
        raise RuntimeError("Couldn't find intellij project .iml file!")
    try:
        return next(path.glob('*.iml'))
    except StopIteration:
        return find_iml_file(path.parent)


def setup_parser(parser):
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--dry-run', action='store_true', help='print to stdout instead of rewriting the file')


def run(args):
    manifest_filename = find_manifest(args.function_name)
    manifest = LambdaManifest(manifest_filename)
    lib_dir = Path(manifest.lib_dir)

    iml_file = find_iml_file(lib_dir)

    with iml_file.open('r') as f:
        data = BeautifulSoup(f, "lxml-xml")

    content = data.module.component.content
    content.clear()

    source_dirs = (
        lib_dir.parent.relative_to(iml_file.parent),
        lib_dir.relative_to(iml_file.parent))

    for source_dir in source_dirs:
        content.append(
            data.new_tag("sourceFolder", isTestSource="false", url="file://$MODULE_DIR$/" + str(source_dir))
        )

    if args.dry_run:
        print(data.prettify())
    else:
        with iml_file.open('w') as f:
            print(data.prettify(), file=f)
