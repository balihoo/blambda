from blambda.utils import findfunc
import unittest
from unittest import mock
from pathlib import Path

root = Path(__file__).parent / 'data' / 'manifests' / 'findfunc'


class TestFindFunc(unittest.TestCase):
    def test_find_all_manifests(self):
        manifests = findfunc.find_all_manifests(root)

        self.assertListEqual(
            [m.full_name for m in manifests],
            ['group1/manifest', 'group1Manifest', 'group1/manifest2', 'group2/manifest', 'group2/manifest3']
        )

    def test_find_manifest(self):
        with mock.patch('blambda.utils.findfunc.get_search_root', return_value=str(root.resolve())):
            self.assertIsNotNone(findfunc.find_manifest('group1Manifest'))
            self.assertIsNotNone(findfunc.find_manifest('group1/group1Manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest'))
            self.assertIsNotNone(findfunc.find_manifest('group1/manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest2'))
            self.assertIsNotNone(findfunc.find_manifest('group1/manifest2'))
            self.assertIsNotNone(findfunc.find_manifest('group2/manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest3'))
            self.assertIsNotNone(findfunc.find_manifest('group2/manifest3'))

            self.assertEqual('group1/manifest', findfunc.find_manifest('manifest').full_name)

        with mock.patch('blambda.utils.findfunc.get_search_root', return_value=str((root / 'group1').resolve())):
            self.assertIsNotNone(findfunc.find_manifest('group1Manifest'))
            self.assertIsNotNone(findfunc.find_manifest('group1/group1Manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest'))
            self.assertIsNotNone(findfunc.find_manifest('group1/manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest2'))
            self.assertIsNotNone(findfunc.find_manifest('group1/manifest2'))
            self.assertIsNone(findfunc.find_manifest('manifest3'))
            self.assertIsNone(findfunc.find_manifest('group2/manifest3'))

            self.assertEqual('group1/manifest', findfunc.find_manifest('manifest').full_name)

        with mock.patch('blambda.utils.findfunc.get_search_root', return_value=str((root / 'group2').resolve())):
            self.assertIsNotNone(findfunc.find_manifest('manifest'))
            self.assertIsNotNone(findfunc.find_manifest('group2/manifest'))
            self.assertIsNotNone(findfunc.find_manifest('manifest3'))
            self.assertIsNotNone(findfunc.find_manifest('group2/manifest3'))
            self.assertIsNone(findfunc.find_manifest('group1Manifest'))
            self.assertIsNone(findfunc.find_manifest('group1/group1Manifest'))

            self.assertEqual('group2/manifest', findfunc.find_manifest('manifest').full_name)
