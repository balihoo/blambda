import unittest
from unittest.mock import patch
from blambda.utils.lambda_manifest import LambdaManifest


@patch('blambda.utils.lambda_manifest.LambdaManifest.load_and_validate', return_value={})
class TestFindFunc(unittest.TestCase):
    def test_manifest_naming(self, mock):
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
