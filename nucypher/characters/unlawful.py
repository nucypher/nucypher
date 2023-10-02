from copy import copy
from unittest import mock
from unittest.mock import Mock, patch

from eth_tester.exceptions import ValidationError
from nucypher_core import NodeMetadata

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Alice, Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import CryptoPower
from nucypher.exceptions import DevelopmentInstallationRequired
from nucypher.policy.payment import FreeReencryptions


class Vladimir(Ursula):
    """
    The power of Ursula, but with a heart forged deep in the mountains of Microsoft or a State Actor or whatever.
    """

    fraud_address = '0xbad022A87Df21E4c787C7B1effD5077014b8CC45'
    fraud_key = 'a75d701cc4199f7646909d15f22e2e0ef6094b3e2aa47a188f35f47e8932a7b9'

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
            raise DevelopmentInstallationRequired(
                importable_name="tests.utils.middleware.EvilMiddleWare"
            )
        eth_blockchain = target_ursula.application_agent.blockchain
        cls.network_middleware = EvilMiddleWare(
            eth_endpoint=eth_blockchain.blockchain_endpoint
        )

        polygon_blockchain = target_ursula.child_application_agent.blockchain

        crypto_power = CryptoPower(power_ups=target_ursula._default_crypto_powerups)

        cls.attach_transacting_key(blockchain=eth_blockchain)

        # Vladimir does not care about payment.
        bogus_pre_payment_method = FreeReencryptions()
        bogus_pre_payment_method.provider = Mock()
        bogus_pre_payment_method.agent = Mock()
        bogus_pre_payment_method.network = TEMPORARY_DOMAIN
        bogus_pre_payment_method.agent.blockchain.client.chain_id = (
            polygon_blockchain.client.chain_id
        )
        mock.patch(
            "mock.interfaces.MockBlockchain.client.chain_id",
            new_callable=mock.PropertyMock(return_value=eth_blockchain.client.chain_id),
        )

        vladimir = cls(
            is_me=True,
            crypto_power=crypto_power,
            domain=TEMPORARY_DOMAIN,
            rest_host=target_ursula.rest_interface.host,
            rest_port=target_ursula.rest_interface.port,
            certificate=target_ursula.certificate,
            network_middleware=cls.network_middleware,
            checksum_address=cls.fraud_address,
            operator_address=cls.fraud_address,
            signer=Web3Signer(eth_blockchain.client),
            eth_endpoint=eth_blockchain.blockchain_endpoint,
            polygon_endpoint=polygon_blockchain.blockchain_endpoint,
            pre_payment_method=bogus_pre_payment_method,
        )

        # Let's use the target's public info, and try to make some changes.

        metadata = target_ursula.metadata()
        metadata_bytes = bytes(metadata)

        # Since it is an object from a Rust extension, we cannot directly modify it,
        # so we have to replace stuff in the byte representation and then deserialize.
        # We are replacing objects with constant size,
        # so it should work regardless of the binary format.

        # Our basic replacement. We want to impersonate the target Ursula.
        metadata_bytes = metadata_bytes.replace(bytes(metadata.payload.staking_provider_address),
                                                vladimir.canonical_address)

        # Use our own verifying key
        if substitute_verifying_key:
            metadata_bytes = metadata_bytes.replace(
                metadata.payload.verifying_key.to_compressed_bytes(),
                vladimir.stamp.as_umbral_pubkey().to_compressed_bytes(),
            )

        fake_metadata = NodeMetadata.from_bytes(metadata_bytes)

        # Re-generate metadata signature using our signing key
        if sign_metadata:
            fake_metadata = NodeMetadata(vladimir.stamp.as_umbral_signer(), fake_metadata.payload)

        # Put metadata back
        vladimir._metadata = fake_metadata

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
