"""
Check for common errors
"""
import importlib.util
import sys

from termcolor import cprint

from .utils.findfunc import find_manifest
from .utils.lambda_manifest import LambdaManifest


def setup_parser(parser):
    parser.add_argument('function_names', nargs='+', type=str, help='the base name of the function')


def run(args):
    for func_name in args.function_names:
        manifest = find_manifest(func_name, fail_if_missing=True)

        if manifest.runtime.startswith('node'):
            cprint(f'skipping {manifest.full_name}, node functions not yet supported', 'yellow')
        else:
            try:
                diff = compare_source_files_to_manifest(manifest)
            except ImportError as e:
                print(e)
                cprint(f"Couldn't import {manifest.full_name}!  Please fix errors and try again", 'red')
            else:
                cprint(manifest.full_name, 'cyan')
                if diff.mismatch:
                    diff.print()
                else:
                    print("Source files match.\n")


def modules_imported_by_lambda_func(manifest: LambdaManifest) -> list:
    importlib.invalidate_caches()
    original_path = sys.path[:]
    try:
        sys.path.insert(0, str(manifest.lib_dir))
        sys.path.insert(0, str(manifest.basedir))
        importlib.import_module(manifest.short_name)
    finally:
        sys.path = original_path[:]

    return [module_.replace('.', '/') + '.py' for module_ in sys.modules]


def files_referenced_in_source(python_source_files, other_files, manifest) -> set:
    """Text-search of the source files to see if any other local files are referenced"""
    out = set()
    for lp in python_source_files:
        contents = (manifest.basedir / lp).read_text()
        for lo in other_files:
            if lo in contents:
                out.add(lo)
    return out


def categorize_local_files(manifest):
    """Categorize the files in the lambda function's directory into two bins:  python files and other files"""
    python = []
    other = []

    for filename in manifest.basedir.iterdir():
        path = filename.relative_to(manifest.basedir)
        if path.suffix == '.py':
            python.append(str(path))
        else:
            other.append(str(path))

    return python, other


def get_required_files(manifest: LambdaManifest) -> set:
    """Try to find which files a given lambda function depends on"""
    python, other = categorize_local_files(manifest)

    # Take all of the local files that were loaded as modules
    suggested_files = {m for m in modules_imported_by_lambda_func(manifest) if m in python}

    # look through all of the imported local python and grab any local files they mention
    return suggested_files | files_referenced_in_source(suggested_files, other, manifest)


class ManifestSourceFileDiff:
    def __init__(self, existing: set, suggested: set):
        self.existing = existing
        self.suggested = suggested
        self.missing_files = self.suggested - self.existing
        self.unnecessary_files = self.existing - self.suggested
        self.mismatch = self.existing != self.suggested

    def print(self):
        if self.missing_files:
            cprint("Missing:", 'red')
            for filename in self.missing_files:
                cprint("  " + filename, 'red')

        if self.unnecessary_files:
            cprint("Possibly Unnecessary:", 'blue')
            for filename in self.unnecessary_files:
                cprint("  " + filename, 'blue')
        print()


def compare_source_files_to_manifest(manifest: LambdaManifest):
    suggested_files = get_required_files(manifest)
    existing_source = set(item[1] if isinstance(item, list) else item
                          for item in manifest.json['source files'])

    return ManifestSourceFileDiff(existing_source, suggested_files)
