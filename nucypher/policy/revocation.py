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

from eth_typing.evm import ChecksumAddress
from eth_utils import to_checksum_address, to_canonical_address

from nucypher_core import RevocationOrder
from nucypher.crypto.signing import SignatureStamp


class RevocationKit:

    def __init__(self, treasure_map, signer: SignatureStamp):
        # TODO: move to core and make a method of TreasureMap?
        self.revocations = dict()
        for staking_provider_address, encrypted_kfrag in treasure_map.destinations.items():
            self.revocations[staking_provider_address] = RevocationOrder(signer=signer.as_umbral_signer(),
                                                                         staking_provider_address=staking_provider_address,
                                                                         encrypted_kfrag=encrypted_kfrag)

    def __iter__(self):
        return iter(self.revocations.values())

    def __getitem__(self, ursula_address: ChecksumAddress):
        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        return self.revocations[to_canonical_address(ursula_address)]

    def __len__(self):
        return len(self.revocations)

    def __eq__(self, other):
        return self.revocations == other.revocations

    @property
    def revokable_addresses(self):
        """Returns a Set of revokable addresses in the checksum address formatting"""
        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        return set([to_checksum_address(address) for address in self.revocations.keys()])

    def add_confirmation(self, ursula_address, signed_receipt):
        """Adds a signed confirmation of Ursula's ability to revoke the node."""
        raise NotImplementedError
