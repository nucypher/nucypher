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


import os

import pytest

from nucypher.core import HRAC, TreasureMap, EncryptedTreasureMap

from nucypher.crypto.powers import DecryptingPower
from nucypher.crypto.umbral_adapter import KeyFrag


def test_complete_treasure_map_journey(federated_alice, federated_bob, federated_ursulas, idle_federated_policy, mocker):

    label = "chili con carne 🔥".encode('utf-8')
    kfrags = idle_federated_policy.kfrags
    ursulas = list(federated_ursulas)[:len(kfrags)]

    hrac = HRAC.derive(publisher_verifying_key=federated_alice.stamp.as_umbral_pubkey(),
                       bob_verifying_key=federated_bob.stamp.as_umbral_pubkey(),
                       label=label)

    assigned_kfrags = {
        ursula.checksum_address: (ursula.public_keys(DecryptingPower), vkfrag)
        for ursula, vkfrag in zip(ursulas, kfrags)}

    treasure_map = TreasureMap.construct_by_publisher(signer=federated_alice.stamp.as_umbral_signer(),
                                                      hrac=hrac,
                                                      policy_encrypting_key=idle_federated_policy.public_key,
                                                      assigned_kfrags=assigned_kfrags,
                                                      threshold=1)

    ursula_rolodex = {u.checksum_address: u for u in ursulas}
    for ursula_address, encrypted_kfrag in treasure_map.destinations.items():
        assert ursula_address in ursula_rolodex
        ursula = ursula_rolodex[ursula_address]
        auth_kfrag = ursula._decrypt_kfrag(encrypted_kfrag)
        auth_kfrag.verify(hrac=treasure_map.hrac,
                          publisher_verifying_key=federated_alice.stamp.as_umbral_pubkey())

    serialized_map = bytes(treasure_map)
    # ...
    deserialized_map = TreasureMap.from_bytes(serialized_map)

    assert treasure_map.destinations == deserialized_map.destinations
    assert treasure_map.hrac == deserialized_map.hrac


    enc_treasure_map = treasure_map.encrypt(signer=federated_alice.stamp.as_umbral_signer(),
                                            recipient_key=federated_bob.public_keys(DecryptingPower))

    enc_serialized_map = bytes(enc_treasure_map)
    # ...
    enc_deserialized_map = EncryptedTreasureMap.from_bytes(enc_serialized_map)

    decrypted_map = federated_bob._decrypt_treasure_map(enc_deserialized_map,
                                                        federated_alice.stamp.as_umbral_pubkey())

    assert treasure_map.threshold == decrypted_map.threshold == 1
    assert treasure_map.destinations == decrypted_map.destinations
    assert treasure_map.hrac == decrypted_map.hrac


@pytest.mark.skip(reason='Backwards-incompatible with umbral 0.2+')
def test_treasure_map_versioning(mocker, federated_alice, federated_bob, federated_ursulas, idle_federated_policy):
    # Produced using f04d564a1
    map_from_previous_version = b'\x87T\x19\xceV_1\x8e\xb0\x87\xf6\xd9\x9d\x80\xba\xaf\xc4\x84\xa1\xd9|P=\x02\x13\xa0r1\x9eB\xf4\xfc\xc6w\xdf\xd1\x88\xc4\x83\x8f \x1c|\xec\xfcnW~k\x95f8\x19\r\xb1\xad\xe9\xa8\xc9\x06\x93j\xaf\xc50&[\xe5Cy\x9cr_R\xcd\xb1\xb1F\xed\x01\x00\x00\x02\xf4\x02][\xb8VP\xfa%D\xc3\xeb\xd4\x8b\xd2SW\x0f\xfe\xe5\x0f\xaa\xe6\x83\x9a\xa1\x91\xf6\x8e\xca\x00\x95\xf9\x90\x02-\x7f\xca\xe8$L\xcd0\x1d\xa1D\x80\xafjY\xea2\xbc\x04\x94\x1c\xd6E\xa4l\x8fu\xdf\x8a#\x04\xe1\x8eKN\xc9Y\xfbB7I\x9b\xa153\xcef\xfd\xb2/9[\x1b^\xe3\xcf\x08/\xf4%k\x06\xf4\xa5\x03\xfa\xf1\xdc\xec\xe1\t\xeb%\x0c\x11{\xbb\xc7Z\xb2^\x1d.\x18\xeaJ\xaa\xa6f\xd8\xb0\x92U\x84;\xbe6\x00\x00\x02m\x89\x97?\xcavL\xa7q\x13\x01\x1e\x1f6\x05)\xc2?\xcd\x96\xafhH/>6\x8d\x1a\xf8\xfd\xd5\x8a\xf9e\xb0\xc5\xa8\xbd(\x86\x9f\xb9L\xb9n=\xcb\xa0\xd2\t\x94\x90l\xc0\xb7\x85\x90N\xe0\xc9M{\x08\xc4\xf5\x80\xb7\xd1\x10\x18P\x8bl\x0f\x87fS\x836\xa6q\'\xabr\xd1l\x1e\xe2\xe7\xce\xccZ1[\x0b\xe7\xaa\x9c\x92Qh"2F\x1f\x9f-7HylC\xad\x03\x8ek_\xb6M\x19\xb2\xef\xde~\xa6\x10F<\xac\x94\xa6e\xc3\xb5\x132\x94\x96\xc4\xd9\'\xf9h\x1c\xe8\xb8Zm\x86M\xed\x00\x86\xc3\xf4\x93\x03/J\x1d6$\x1a\xe5+\xad\xf93\x17n\xc3\x19sQ2C\xaf\x9d\x89p\xb9557O\x9a\xc3O\xf0\x1f\xb3M.\xa9\x89\xeb\xb9\xf6\xe8\xcc@\xb0\\)\x9d\xdb\'\xfc\xc4_\xfd\xe1\xef\x01\xe3\xe7va\xac\xd7y\xb2\xcfm\xda\x85\x06(\x92H\xe2p\xf1\x9aw\xaf\x83\x1c\xd3@a\xaa\xf6\xee\xfc\xae&;\xdd*\x94I\'r1JG\xca\xdb\x9e\xef\x18Z\x9f\x15\x81\xe3\x1c\xcfJ\xd6;2H\xe8\xed\xfc\x98\x8e\xc6\x94\x1f\x1d\x95A\xa5\x8e\xe5\xc6f\x85\xbb\xc3\xd0\x9d\x83\xd3\xdf\x91]\x16\xe6)\xfa\xc0\xf3\xba\x7fAb\x81\xe0\x8f\x1bu0\x0b\x82^\xe9\x16\xf0\xfc\xc3p\xd4\x9f\'\xa6\xe5\xb4\xf7\xe1\x99\xa5\xfe\x12\x0e{L\xb0\xd6\xa1\x049\xcf\xe0\xca\x06\xe3\xd6u\x9e\xb3P\xb7\x1a\xc5X\xb7\xb2\xfa\x1dJ\xe1\xa9Gb\xf6l~DG\x8e5X\xc2^\x87\xac\x89W(\xaf\xd3\x15o\xde\xf7\xe4\x18\xd9\x98\xc3\tcL\xd3\x9dF\x8e3\xe5u\x03\x0b\xe7\tj\xdb\xd3B\xa1\x85\x9d \x9c\xa4{n\x01"\xab\xe1509\xdaoL\xc9\x8d\xc9\xfd"\xad\xd8\xfd\xf5\x14\xa2\xa8N\xf5\xa0\xf4\x04Y\x85i\xe0zj34\xc9\xbd\xac\xb9gn\x19J]\x0eL\x81C\xb9\x95\x86Q,\x81\xdf\xcbh\x13\xae8\xe8\x06y\xd1\xcd\x867\x1a\x1c\xe1\x05\xba\xfaL\x1a\x1f\x9f~\x18O1p@\xee\xee\xc4\xed\x84%\xb4\xb4\x12\xb6\x81\x0c\xcamf.\x9c\xe1\xfe\xc4\x87I\'\xc7e\xc1\x7f\xeb\x9c\xe1\xca\xa5\r.\x15\xa8r\xa8\x82Q\x13\x99K\x12X3\x04\xbc\x99\x96\xf8\xc3\x1es\x0c\x85\x8d\xd3\xee\x1b^\xc8\xf5\x1d^\x1a&6#\xbc\xa8~wp}]8\xb5\xe6v\xa4D\xfe:\xb8<q\xd9\x02\xfa\x7f\xcfWA\xad\xd1#\xac\x8b\xd7\xff\xca\xf7[dm\x9b\x06\xcc\x03\x1b\xfa\xd1\xf6:\xad\x1c\xb6\xb8'

    kfrags = idle_federated_policy.kfrags[:3]

    hrac = HRAC.derive(publisher_verifying_key=federated_alice.stamp.as_umbral_pubkey(),
                       bob_verifying_key=federated_bob.stamp.as_umbral_pubkey(),
                       label=label)

    assigned_kfrags = {
        ursula.checksum_address: (ursula.public_keys(DecryptingPower), vkfrag)
        for ursula, vkfrag in zip(list(federated_ursulas)[:len(kfrags)], kfrags)}

    treasure_map = TreasureMap.construct_by_publisher(signer=federated_alice.stamp.as_umbral_signer(),
                                                      hrac=hrac,
                                                      policy_encrypting_key=idle_federated_policy.public_key,
                                                      assigned_kfrags=assigned_kfrags,
                                                      threshold=2)

    # Good version (baseline)
    serialized_map = bytes(treasure_map)
    deserialized_map = TreasureMap.from_bytes(serialized_map)
    assert treasure_map == deserialized_map

    map_from_f04d564a1 = TreasureMap.from_bytes(map_from_previous_version)
    assert map_from_f04d564a1.public_verify()
