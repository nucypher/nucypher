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


import tempfile
from copy import copy
from unittest.mock import patch

from eth_tester.exceptions import ValidationError

from nucypher.core import NodeMetadata

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Alice, Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import CryptoPower, SigningPower
from nucypher.exceptions import DevelopmentInstallationRequired


class Vladimir(Ursula):
    """
    The power of Ursula, but with a heart forged deep in the mountains of Microsoft or a State Actor or whatever.
    """

    fraud_address = '0xbad022A87Df21E4c787C7B1effD5077014b8CC45'
    fraud_key = 'a75d701cc4199f7646909d15f22e2e0ef6094b3e2aa47a188f35f47e8932a7b9'
    db_filepath = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checksum_address = self.fraud_address

    @classmethod
    def from_target_ursula(cls,
                           target_ursula: Ursula,
                           substitute_verifying_key: bool = False,
                           sign_metadata: bool = False,
                           ) -> 'Vladimir':
        """
        Sometimes Vladimir seeks to attack or imitate a *specific* target Ursula.

        TODO: This is probably a more instructive method if it takes a bytes representation instead of the entire Ursula.
        """
        try:
            from tests.utils.middleware import EvilMiddleWare
        except ImportError:
            raise DevelopmentInstallationRequired(importable_name='tests.utils.middleware.EvilMiddleWare')
        cls.network_middleware = EvilMiddleWare()

        crypto_power = CryptoPower(power_ups=target_ursula._default_crypto_powerups)

        blockchain = target_ursula.policy_agent.blockchain
        cls.attach_transacting_key(blockchain=blockchain)

        db_filepath = tempfile.mkdtemp(prefix='Vladimir')

        vladimir = cls(is_me=True,
                       crypto_power=crypto_power,
                       db_filepath=db_filepath,
                       domain=TEMPORARY_DOMAIN,
                       rest_host=target_ursula.rest_interface.host,
                       rest_port=target_ursula.rest_interface.port,
                       certificate=target_ursula.certificate,
                       network_middleware=cls.network_middleware,
                       checksum_address=cls.fraud_address,
                       worker_address=cls.fraud_address,
                       signer=Web3Signer(blockchain.client),
                       provider_uri=blockchain.provider_uri,
                       )

        # Let's use the target's public info, and try to make some changes.
        # We are going to mutate it, so make a copy (it is cached in the Ursula).
        metadata = NodeMetadata.from_bytes(bytes(target_ursula.metadata()))
        metadata_payload = metadata._metadata_payload

        # Our basic replacement. We want to impersonate the target Ursula.
        metadata_payload = metadata_payload._replace(public_address=vladimir.canonical_public_address)

        # Use our own verifying key
        if substitute_verifying_key:
            metadata_payload = metadata_payload._replace(
                verifying_key=vladimir.stamp.as_umbral_pubkey())

        # Re-generate metadata signature using our signing key
        if sign_metadata:
            signature = vladimir.stamp(bytes(metadata_payload))
        else:
            signature = metadata.signature

        # Put metadata back
        vladimir._metadata = NodeMetadata(signature, metadata_payload)

        return vladimir

    @classmethod
    def attach_transacting_key(cls, blockchain):
        """
        Upload Vladimir's ETH keys to the keychain via web3.
        """
        try:
            password = 'iamverybadass'
            blockchain.w3.provider.ethereum_tester.add_account(cls.fraud_key, password=password)
        except (ValidationError,):
            # check if Vlad's key is already on the keystore...
            if cls.fraud_address in blockchain.client.accounts:
                return True
            else:
                raise
        return True


class Amonia(Alice):
    """
    Separated at birth, Alice's sister is lighter than air and has a pungent smell.
    """

    @classmethod
    def from_lawful_alice(cls, alice):
        alice_clone = copy(alice)
        alice_clone.__class__ = cls
        return alice_clone

    def grant_without_paying(self, *args, **kwargs):
        """I take what I want for free."""

        def what_do_you_mean_you_dont_tip(policy, *args, **kwargs):
            return b"He convinced me, gimme back my $"

        with patch("nucypher.policy.policies.BlockchainPolicy._publish", what_do_you_mean_you_dont_tip):
            return super().grant(*args, **kwargs)

    def circumvent_safegaurds_and_grant_without_paying(self, *args, **kwargs):
        """
        I am not Alice, and I needn't abide by her sensibilities or raise her Exceptions.

        Can I grant for free if I change the client code to my liking?
        """
        with patch("nucypher.policy.policies.Policy._publish", self.grant_without_paying):
            return self.grant_without_paying(*args, **kwargs)

    def grant_while_paying_the_wrong_nodes(self,
                                           ursulas_to_trick_into_working_for_free,
                                           ursulas_to_pay_instead,
                                           *args, **kwargs):
        """
        Instead of paying the nodes with whom I've made Arrangements,
        I'll pay my flunkies instead.  Since this is a valid transaction and creates
        an on-chain Policy using PolicyManager, I'm hoping Ursula won't notice.
        """

        def publish_wrong_payee_address_to_blockchain(policy, ursulas):
            receipt = policy.publisher.policy_agent.create_policy(
                policy_id=bytes(policy.hrac),  # bytes16 _policyID
                transacting_power=policy.publisher.transacting_power,
                value=policy.value,
                end_timestamp=policy.expiration.epoch,  # uint16 _numberOfPeriods
                node_addresses=[f.checksum_address for f in ursulas_to_pay_instead]  # address[] memory _nodes
            )

            return receipt['transactionHash']

        with patch("nucypher.policy.policies.BlockchainPolicy._publish",
                   publish_wrong_payee_address_to_blockchain):
            return super().grant(ursulas=ursulas_to_trick_into_working_for_free, *args, **kwargs)
