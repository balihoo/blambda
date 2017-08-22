"""
Insert a function's base / lib dirs into intellij's indexing path. This works by rewriting the project's
*.iml file, inserting the proper paths as source directories.
"""
from pathlib import Path

from bs4 import BeautifulSoup
from termcolor import cprint

from .utils.base import die
from .utils.findfunc import find_manifest


def find_iml_file(path: Path) -> Path:
    # if you hit '/', then give up
    if str(path) == path.anchor:
        die("Couldn't find intellij project .iml file!", 'red')

    # look for an .idea directory for older versions of intellij
    idea_dir = (path / '.idea')
    if idea_dir.is_dir():
        try:
            return next(idea_dir.glob('*.iml'))
        except StopIteration:
            pass

    # keep looking in parent directories until you find the .iml file
    try:
        return next(path.glob('*.iml'))
    except StopIteration:
        return find_iml_file(path.parent)


def setup_parser(parser):
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--dry-run', action='store_true', help='print to stdout instead of rewriting the file')


def run(args):
    manifest = find_manifest(args.function_name)
    if manifest is None:
        cprint("Couldn't find manifest for " + args.function_name, 'red')
        exit(1)

    iml_file = find_iml_file(manifest.basedir)

    with iml_file.open('r') as f:
        data = BeautifulSoup(f, "lxml-xml")

    content = data.module.component.content
    content.clear()

    # we need directories relative to project root, not the .idea directory
    parent_dir = iml_file.parent.parent if iml_file.parent.name == '.idea' else iml_file.parent

    source_dirs = (
        manifest.basedir.relative_to(parent_dir),
        manifest.lib_dir.relative_to(parent_dir),
        manifest.node_dir.relative_to(parent_dir),
    )

    for source_dir in source_dirs:
        content.append(
            data.new_tag("sourceFolder", isTestSource="false", url="file://$MODULE_DIR$/" + str(source_dir))
        )

    if "node" in manifest.runtime:
        (manifest.basedir / "node_modules").symlink_to(manifest.node_dir)

    if args.dry_run:
        print(data.prettify())
    else:
        iml_file.write_text(data.prettify())
