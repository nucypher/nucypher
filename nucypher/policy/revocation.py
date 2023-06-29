


from eth_typing.evm import ChecksumAddress
from eth_utils import to_canonical_address, to_checksum_address
from nucypher_core import Address, RevocationOrder

from nucypher.crypto.signing import SignatureStamp


class RevocationKit:

    def __init__(self, treasure_map, signer: SignatureStamp):
        # TODO: move to core and make a method of TreasureMap?
        self.revocations = dict()
        for staking_provider_address, encrypted_kfrag in treasure_map.destinations.items():
            address = Address(to_canonical_address(bytes(staking_provider_address)))
            self.revocations[staking_provider_address] = RevocationOrder(signer=signer.as_umbral_signer(),
                                                                         staking_provider_address=address,
                                                                         encrypted_kfrag=encrypted_kfrag)

    def __iter__(self):
        return iter(self.revocations.values())

    def __getitem__(self, ursula_address: ChecksumAddress):
        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        return self.revocations[Address(to_canonical_address(ursula_address))]

    def __len__(self):
        return len(self.revocations)

    def __eq__(self, other):
        return self.revocations == other.revocations

    @property
    def revokable_addresses(self):
        """Returns a Set of revokable addresses in the checksum address formatting"""
        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        return set([to_checksum_address(bytes(address)) for address in self.revocations.keys()])

    def add_confirmation(self, ursula_address, signed_receipt):
        """Adds a signed confirmation of Ursula's ability to revoke the node."""
        raise NotImplementedError
