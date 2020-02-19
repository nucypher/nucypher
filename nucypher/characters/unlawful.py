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
from copy import copy
from unittest.mock import patch

from eth_tester.exceptions import ValidationError

from nucypher.characters.lawful import Ursula, Alice
from nucypher.crypto.powers import CryptoPower, SigningPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_URSULA_DB_FILEPATH
from nucypher.utilities.sandbox.middleware import EvilMiddleWare


class Vladimir(Ursula):
    """
    The power of Ursula, but with a heart forged deep in the mountains of Microsoft or a State Actor or whatever.
    """

    network_middleware = EvilMiddleWare()
    fraud_address = '0xbad022A87Df21E4c787C7B1effD5077014b8CC45'
    fraud_key = 'a75d701cc4199f7646909d15f22e2e0ef6094b3e2aa47a188f35f47e8932a7b9'
    db_filepath = MOCK_URSULA_DB_FILEPATH

    @classmethod
    def from_target_ursula(cls,
                           target_ursula: Ursula,
                           claim_signing_key: bool = False,
                           attach_transacting_key: bool = True
                           ) -> 'Vladimir':
        """
        Sometimes Vladimir seeks to attack or imitate a *specific* target Ursula.

        TODO: This is probably a more instructive method if it takes a bytes representation instead of the entire Ursula.
        """
        crypto_power = CryptoPower(power_ups=target_ursula._default_crypto_powerups)

        if claim_signing_key:
            crypto_power.consume_power_up(SigningPower(pubkey=target_ursula.stamp.as_umbral_pubkey()))

        if attach_transacting_key:
            cls.attach_transacting_key(blockchain=target_ursula.blockchain)

        vladimir = cls(is_me=True,
                       crypto_power=crypto_power,
                       db_filepath=cls.db_filepath,
                       rest_host=target_ursula.rest_interface.host,
                       rest_port=target_ursula.rest_interface.port,
                       certificate=target_ursula.rest_server_certificate(),
                       network_middleware=cls.network_middleware,
                       checksum_address=cls.fraud_address,
                       worker_address=cls.fraud_address,
                       ######### Asshole.
                       timestamp=target_ursula._timestamp,
                       interface_signature=target_ursula._interface_signature,
                       #########
                       )

        return vladimir

    @classmethod
    def attach_transacting_key(cls, blockchain):
        """
        Upload Vladimir's ETH keys to the keychain via web3.
        """
        try:
            password = INSECURE_DEVELOPMENT_PASSWORD
            blockchain.w3.provider.ethereum_tester.add_account(cls.fraud_key, password=password)
        except (ValidationError,):
            # check if Vlad's key is already on the keyring...
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

    @staticmethod
    def enact_without_tabulating_responses(policy, network_middleware, *_args, **_kwargs):
        for arrangement in policy._Policy__assign_kfrags():
            arrangement_message_kit = arrangement.encrypt_payload_for_ursula()
            try:
                network_middleware.enact_policy(arrangement.ursula,
                                                arrangement.id,
                                                arrangement_message_kit.to_bytes())
            except Exception as e:
                # I don't care what went wrong - I will keep trying to ram arrangements through.
                continue

    def grant_without_paying(self, *args, **kwargs):
        """
        I take what I want for free.
        """

        def what_do_you_mean_you_dont_tip(policy, *args, **kwargs):
            policy.publish_transaction = b"He convinced me, gimme back my $"

        with patch("nucypher.policy.policies.BlockchainPolicy.publish_to_blockchain", what_do_you_mean_you_dont_tip):
            return super().grant(*args, **kwargs)

    def circumvent_safegaurds_and_grant_without_paying(self, *args, **kwargs):
        """
        I am not Alice, and I needn't abide by her sensibilities or raise her Exceptions.

        Can I grant for free if I change the client code to my liking?
        """
        with patch("nucypher.policy.policies.Policy.enact", self.enact_without_tabulating_responses):
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

        def publish_wrong_payee_address_to_blockchain(policy, *args, **kwargs):
            receipt = policy.author.policy_agent.create_policy(
                policy_id=policy.hrac()[:16],  # bytes16 _policyID
                author_address=policy.author.checksum_address,
                value=policy.value,
                end_timestamp=policy.expiration.epoch,  # uint16 _numberOfPeriods
                node_addresses=[f.checksum_address for f in ursulas_to_pay_instead]  # address[] memory _nodes
            )

            # Capture Response
            policy.receipt = receipt
            policy.publish_transaction = receipt['transactionHash']
            policy.is_published = True

            return receipt

        with patch("nucypher.policy.policies.BlockchainPolicy.publish_to_blockchain",
                   publish_wrong_payee_address_to_blockchain):
            with patch("nucypher.policy.policies.Policy.enact", self.enact_without_tabulating_responses):
                return super().grant(handpicked_ursulas=ursulas_to_trick_into_working_for_free, *args, **kwargs)
