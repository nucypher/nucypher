from eth_tester.exceptions import ValidationError

from nucypher.characters.lawful import Ursula
from nucypher.crypto.powers import CryptoPower, SigningPower
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.middleware import EvilMiddleWare


class Vladimir(Ursula):
    """
    The power of Ursula, but with a heart forged deep in the mountains of Microsoft or a State Actor or whatever.
    """

    network_middleware = EvilMiddleWare()
    fraud_address = '0xbad022A87Df21E4c787C7B1effD5077014b8CC45'
    fraud_key = 'a75d701cc4199f7646909d15f22e2e0ef6094b3e2aa47a188f35f47e8932a7b9'

    @classmethod
    def from_target_ursula(cls, target_ursula, claim_signing_key=False):
        """
        Sometimes Vladimir seeks to attack or imitate a *specific* target Ursula.

        TODO: This is probably a more instructive method if it takes a bytes representation instead of the entire Ursula.
        """
        crypto_power = CryptoPower(power_ups=Ursula._default_crypto_powerups)

        if claim_signing_key:
            crypto_power.consume_power_up(SigningPower(pubkey=target_ursula.stamp.as_umbral_pubkey()))

        vladimir = cls(crypto_power=crypto_power,
                       rest_host=target_ursula.rest_information()[0].host,
                       rest_port=target_ursula.rest_information()[0].port,
                       checksum_address=cls.fraud_address,
                       certificate=target_ursula.rest_server_certificate(),
                       is_me=False)

        # Asshole.
        vladimir._interface_signature_object = target_ursula._interface_signature_object
        vladimir._timestamp = target_ursula._timestamp

        cls.attach_transacting_key(blockchain=target_ursula.blockchain)

        return vladimir

    @classmethod
    def attach_transacting_key(cls, blockchain):
        """
        Upload Vladimir's ETH keys to the keychain via web3 / RPC.
        """
        try:
            passphrase = TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD
            blockchain.interface.w3.personal.importRawKey(private_key=cls.fraud_key, passphrase=passphrase)
        except (ValidationError, ):
            # check if Vlad's key is already on the keyring...
            if cls.fraud_address in blockchain.interface.w3.personal.listAccounts:
                return True
            else:
                raise
        return True
