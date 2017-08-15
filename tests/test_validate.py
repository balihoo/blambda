from pathlib import Path
from unittest import TestCase

from blambda.utils.lambda_manifest import LambdaManifest
from blambda.validate import compare_source_files_to_manifest


class TestValidation(TestCase):
    def test_flat(self):
        manifest = LambdaManifest(Path(__file__).parent / 'data' / 'validate' / 'validate_testcase.json')
        diff = compare_source_files_to_manifest(manifest)
        self.assertTrue(diff.mismatch)
        self.assertSetEqual(diff.suggested, {'whoops_forgot_this.py', 'validate_testcase.py', 'include.py'})
        self.assertSetEqual(diff.unnecessary_files, {'not_necessary.py'})
        self.assertSetEqual(diff.missing_files, {'whoops_forgot_this.py'})
