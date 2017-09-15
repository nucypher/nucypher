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

    def step1_test_header_defaults(self):
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

    def step2_test_header_update(self):
        new_header = {
            'version': 200,
            'keys': [b'test'],
            'chunk_size': 999,
        }
        self.header_obj.update_header(header=new_header)

        self.assertEqual(200, self.header['version'])
        self.assertEqual(1, len(self.header['keys']))
        self.assertEqual(b'test', self.header['keys'][0])
        self.assertEqual(999, self.header['chunk_size'])

        # Check that the non-updated num_chunks value didn't change
        self.assertEqual(0, self.header['num_chunks'])

    def step3_test_header_read(self):
        header = Header(b'test_header.nuc.header').header

        self.assertEqual(200, header[b'version'])
        self.assertEqual(1, len(header[b'keys']))
        self.assertEqual(b'test', header[b'keys'][0])
        self.assertEqual(999, header[b'chunk_size'])
        self.assertEqual(0, header[b'num_chunks'])

    def _steps(self):
        for attr in sorted(dir(self)):
            if not attr.startswith('step'):
                continue
            yield attr

    def test_header(self):
        for _s in self._steps():
            try:
                getattr(self, _s)()
            except Exception as e:
                self.fail('{} failed({})'.format(_s, e))
