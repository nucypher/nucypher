"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from cryptography.hazmat.primitives.asymmetric import ec

from nucypher.config.keyring import _assemble_key_data, _PrivateKeySerializer, _generate_tls_keys, \
    _TLSPrivateKeySerializer


def test_private_key_serialization():
    key_data = _assemble_key_data(key_data=b'peanuts, get your peanuts',
                                  master_salt=b'sea salt',
                                  wrap_salt=b'red salt')
    key_bytes = _PrivateKeySerializer.serialize(key_data)
    deserialized_key_data = _PrivateKeySerializer.deserialize(key_bytes)

    assert key_data == deserialized_key_data


def test_tls_private_key_serialization():
    host = '127.0.0.1'
    checksum_address = '0xdeadbeef'
    curve = ec.SECP384R1

    private_key, _ = _generate_tls_keys(host=host,
                                        checksum_address=checksum_address,
                                        curve=curve)
    password = b'serialize_deserialized'
    key_bytes = _TLSPrivateKeySerializer.serialize(private_key, password=password)
    deserialized_private_key = _TLSPrivateKeySerializer.deserialize(key_bytes, password=password)

    assert private_key.private_numbers() == deserialized_private_key.private_numbers()

    # just to be certain that a different key doesn't have the same private numbers
    other_private_key, _ = _generate_tls_keys(host=host,
                                              checksum_address=checksum_address,
                                              curve=curve)
    assert other_private_key.private_numbers() != deserialized_private_key.private_numbers()
