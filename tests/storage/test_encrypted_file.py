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
