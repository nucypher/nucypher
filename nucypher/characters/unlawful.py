"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
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
    db_name = 'vladimir.db'

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
                       db_name=cls.db_name,
                       db_filepath=cls.db_name,
                       rest_host=target_ursula.rest_information()[0].host,
                       rest_port=target_ursula.rest_information()[0].port,
                       certificate=target_ursula.rest_server_certificate(),
                       network_middleware=cls.network_middleware,
                       checksum_address = cls.fraud_address,
                       ######### Asshole.
                       timestamp=target_ursula._timestamp,
                       interface_signature=target_ursula._interface_signature_object,
                       ######### 
                       )

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
