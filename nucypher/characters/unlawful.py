from nucypher.characters.lawful import Ursula
from nucypher.crypto.powers import CryptoPower
from nucypher.utilities.sandbox.middleware import EvilMiddleWare


class Vladimir(Ursula):
    """
    The power of Ursula, but with a heart forged deep in the mountains of Microsoft or a State Actor or whatever.
    """

    network_middleware = EvilMiddleWare()

    @classmethod
    def from_target_ursula(cls, target_ursula):
        """
        Sometimes Vladimir seeks to attack or imitate


        a *specific* target Ursula.
        """
        vladimir = cls(crypto_power=CryptoPower(power_ups=Ursula._default_crypto_powerups),
                          rest_host=target_ursula.rest_information()[0].host,
                          rest_port=target_ursula.rest_information()[0].port,
                          checksum_address='0x0000badbadbadbad0000bad00bad00bad0000000',  # Fradulent address
                          certificate=target_ursula.rest_server_certificate(),
                          is_me=False)
        vladimir._interface_signature_object = target_ursula._interface_signature_object  # Asshole.
        return vladimir
