import unittest
import os
from nkms.storage import EncryptedFile
from nacl.utils import random


class TestEncryptedFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = random(32)
        cls.path = b'test.nuc'
        cls.header_path = b'test.nuc.header'
        cls.enc_file_obj = EncryptedFile(cls.key, cls.path, cls.header_path)

    @classmethod
    def tearDownClass(cls):
        os.remove(b'test.nuc')
        os.remove(b'test.nuc.header')

    def setUp(self):
        self.enc_file = TestEncryptedFile.enc_file_obj
        self.header = TestEncryptedFile.enc_file_obj.header

    def step1_update_header(self):
        pass

    def _steps(self):
        for attr in sorted(dir(self)):
            if not attr.startswith('step'):
                continue
            yield attr

    def test_encrypted_file(self):
        for _s in self._steps():
            try:
                getattr(self, _s)()
            except Exception as e:
                self.fail('{} failed({})'.format(_s, e))
