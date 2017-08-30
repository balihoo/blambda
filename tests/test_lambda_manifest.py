import unittest
from pathlib import Path

from blambda.utils.lambda_manifest import LambdaManifest


class TestFindFunc(unittest.TestCase):
    def test_manifest_naming(self):
        test_cases = [
            ['adwords/textad.json', 'adwords/textad', 'textad', 'adwords', 'adwords_textad'],
            ['timezone/timezone.json', 'timezone', 'timezone', 'timezone', 'timezone'],
            ['echo/echo_worker.json', 'echo_worker', 'echo_worker', 'echo', 'echo_worker'],
            ['worker/some_worker.json', 'worker/some_worker', 'some_worker', 'worker', 'worker_some_worker'],
        ]

        for (path, full, short, group, deployed) in test_cases:
            with self.subTest(manifest=path):
                m = LambdaManifest(path)
                self.assertEqual(m.full_name, full)
                self.assertEqual(m.short_name, short)
                self.assertEqual(m.group, group)
                self.assertEqual(m.deployed_name, deployed)

    def test_source_files(self):
        """Make sure the 'source files' section of the manifest is properly handled in the 'blambda deps' case"""

        root = Path(__file__).parent / 'data' / 'manifests'
        path = root / 'source_files.json'
        manifest = LambdaManifest(path)

        expect = [
            ((root / '../shared/a.coffee'), (root / 'a.coffee')),
            ((root / '../shared/shared.txt'), (root / 'shared.txt')),
            ((root / '../shared/shared.txt'), (root / 'shared.txt')),
        ]
        for src, dest in manifest.source_files():
            src_expect, dest_expect = expect.pop(0)
            self.assertEqual(src.resolve(), src_expect.resolve())
            self.assertEqual(dest.resolve(), dest_expect.resolve())

    def test_source_files_deploy(self):
        """Make sure the 'source files' section of the manifest is properly handled in the 'blambda deploy' case"""

        root = Path(__file__).parent / 'data' / 'manifests'
        path = root / 'source_files.json'
        manifest = LambdaManifest(path)

        outdir = Path('/tmp')

        expect = [
            ((root / 'testfile.coffee'), (outdir / 'testfile.coffee')),
            ((root / 'plaincopy.txt'), (outdir / 'plaincopy.txt')),
            ((root / '../shared/a.coffee'), (outdir / 'a.coffee')),
            ((root / '../shared/shared.txt'), (outdir / 'shared.txt')),
            ((root / '../shared/shared.txt'), (outdir / 'shared.txt')),
        ]
        for src, dest in manifest.source_files(dest_dir=outdir):
            src_expect, dest_expect = expect.pop(0)
            self.assertEqual(src.resolve(), src_expect.resolve())
            self.assertEqual(dest.resolve(), dest_expect.resolve())
