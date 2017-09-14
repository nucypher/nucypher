import unittest
import pathlib
import msgpack
import os
from nkms.storage import Header


class TestHeader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = Header(b'test_header.nuc.header')

    @classmethod
    def tearDownClass(cls):
        os.remove(b'test_header.nuc.header')

    def setUp(self):
        self.header_obj = TestHeader.header
        self.header = TestHeader.header.header

    def test_header_defaults(self):
        # Test dict values
        self.assertEqual(100, self.header['version'])
        self.assertEqual(20, len(self.header['nonce']))
        self.assertEqual(list, type(self.header['keys']))
        self.assertEqual(0, len(self.header['keys']))
        self.assertEqual(1000000, self.header['chunk_size'])
        self.assertEqual(0, self.header['num_chunks'])

        # Test path
        self.assertEqual(b'test_header.nuc.header', self.header_obj.path)

        # Test that the header exists on the filesystem
        self.assertTrue(pathlib.Path(self.header_obj.path.decode()).is_file())

        # Grab the nonce value for the next tests
        self.nonce = self.header['nonce']
