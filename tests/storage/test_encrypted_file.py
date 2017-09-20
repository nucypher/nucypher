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
        cls.data = random(30)
        cls.enc_file_obj = EncryptedFile(cls.key, cls.path, cls.header_path)

    @classmethod
    def tearDownClass(cls):
        os.remove(b'test.nuc')
        os.remove(b'test.nuc.header')

    def setUp(self):
        self.enc_file = TestEncryptedFile.enc_file_obj
        self.header = TestEncryptedFile.enc_file_obj.header
        self.header_obj = TestEncryptedFile.enc_file_obj.header_obj

    def step1_update_header(self):
        updated_header = {'chunk_size': 10}
        self.header_obj.update_header(header=updated_header)
        self.assertEqual(10, self.header['chunk_size'])

    def step2_write_data(self):
        # Writes the equivalent of three chunks per the updated header
        chunks_written = self.enc_file.write(TestEncryptedFile.data)
        self.assertEqual(3, chunks_written)

        self.enc_file.close()
        with open('test.nuc', 'rb') as f:
            file_data = f.read()
        self.assertFalse(TestEncryptedFile.data in file_data)

    def step3_read_chunk(self):
        enc_file = EncryptedFile(TestEncryptedFile.key, TestEncryptedFile.path,
                                 TestEncryptedFile.header_path)
        chunks = enc_file.read(num_chunks=1)
        self.assertEqual(1, len(chunks))
        self.assertTrue(chunks[0] in TestEncryptedFile.data)
        enc_file.close()

    def step4_read_all_chunks(self):
        enc_file = EncryptedFile(TestEncryptedFile.key, TestEncryptedFile.path,
                                 TestEncryptedFile.header_path)
        chunks = enc_file.read()
        self.assertEqual(3, len(chunks))
        self.assertTrue(chunks[0] in TestEncryptedFile.data)
        self.assertTrue(chunks[1] in TestEncryptedFile.data)
        self.assertTrue(chunks[2] in TestEncryptedFile.data)
        enc_file.close()

    def step5_append_data_and_read(self):
        enc_file = EncryptedFile(TestEncryptedFile.key, TestEncryptedFile.path,
                                 TestEncryptedFile.header_path)
        data = random(20)
        written_chunks = enc_file.write(data)
        self.assertEqual(2, written_chunks)
        enc_file.close()

        # After closing the object, we create another to read the data
        enc_file = EncryptedFile(TestEncryptedFile.key, TestEncryptedFile.path,
                                 TestEncryptedFile.header_path)
        chunks = enc_file.read()
        self.assertEqual(5, len(chunks))
        self.assertTrue(chunks[0] in TestEncryptedFile.data)
        self.assertTrue(chunks[1] in TestEncryptedFile.data)
        self.assertTrue(chunks[2] in TestEncryptedFile.data)
        self.assertTrue(chunks[3] in data)
        self.assertTrue(chunks[4] in data)
        enc_file.close()

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
