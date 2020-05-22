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

import random
import time
import msgpack

from nucypher.characters.lawful import Enrico


HEART_DATA_FILENAME = 'heart_data.msgpack'


def generate_heart_rate_samples(policy_pubkey,
                                samples: int = 500,
                                save_as_file: bool = False):
    data_source = Enrico(policy_encrypting_key=policy_pubkey)

    data_source_public_key = bytes(data_source.stamp)

    heart_rate = 80
    now = time.time()

    kits = list()
    for _ in range(samples):
        # Simulated heart rate data
        # Normal resting heart rate for adults: between 60 to 100 BPM
        heart_rate = random.randint(max(60, heart_rate-5),
                                    min(100, heart_rate+5))
        now += 3

        heart_rate_data = {
            'heart_rate': heart_rate,
            'timestamp': now,
        }

        plaintext = msgpack.dumps(heart_rate_data, use_bin_type=True)
        message_kit, _signature = data_source.encrypt_message(plaintext)

        kit_bytes = message_kit.to_bytes()
        kits.append(kit_bytes)

    data = {
        'data_source': data_source_public_key,
        'kits': kits,
    }

    if save_as_file:
        with open(HEART_DATA_FILENAME, "wb") as file:
            msgpack.dump(data, file, use_bin_type=True)

    return data
