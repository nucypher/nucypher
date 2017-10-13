from kademlia.network import Server
from nkms.crypto import api
from nkms.crypto.constants import NOT_SIGNED, NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningKeypair
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server
    _actor_mapping = {}
    _default_crypto_powerups = None

    class NotFound(KeyError):
        """raised when we try to interact with an actor of whom we haven't learned yet."""

    def __init__(self, attach_server=True, crypto_power: CryptoPower = None,
                 crypto_power_ups=[]):
        """
        :param attach_server:  Whether to attach a Server when this Character is born.
        :param crypto_power: A CryptoPower object; if provided, this will be the character's CryptoPower.
        :param crypto_power_ups:  If crypto_power is not provided, a new CryptoPower will be made and
            will consume all of the CryptoPowerUps in this list.

        If neither crypto_power nor crypto_power_ups are provided, we give this Character all CryptoPowerUps
        listed in their _default_crypto_powerups attribute.
        """
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        if attach_server:
            self.attach_server()
        if crypto_power:
            self._crypto_power = crypto_power
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(self._default_crypto_powerups)

        class Seal(object):
            """
            Can be called to sign something or used to express the signing public key as bytes.
            """

            def __call__(seal_instance, *messages_to_sign):
                return self._crypto_power.sign(*messages_to_sign)

            def as_bytes(seal_instance):
                return self._crypto_power.pubkey_sig_bytes()

            def as_tuple(self_instance):
                return self._crypto_power.pubkey_sig_tuple()

        self.seal = Seal()

    def attach_server(self, ksize=20, alpha=3, id=None, storage=None,
                      *args, **kwargs) -> None:
        self._server = self._server_class(ksize, alpha, id, storage, *args, **kwargs)

    @property
    def server(self) -> Server:
        if self._server:
            return self._server
        else:
            raise RuntimeError("Server hasn't been attached.")

    def learn_about_actor(self, actor):
        self._actor_mapping[actor.id()] = actor

    def encrypt_for(self, recipient: str, cleartext: bytes, sign: bool = True,
                    sign_cleartext=True, cheat=False) -> tuple:
        """
        Looks up recipient actor, finds that actor's pubkey_enc on our keyring, and encrypts for them.
        Optionally signs the message as well.

        :param recipient: The character whose public key will be used to encrypt cleartext.
        :param cleartext: The secret    to be encrypted.
        :param sign: Whether or not to sign the message.
        :param sign_cleartext: When signing, the cleartext is signed if this is True,  Otherwise, the resulting ciphertext is signed.
        :return: A tuple, (ciphertext, signature).  If sign==False, then signature will be NOT_SIGNED.
        """
        actor = self._lookup_actor(recipient)
        pubkey_sign_id = actor.seal()  # I don't even like this.  I prefer .seal(), which

        if cheat:
            ciphertext = b"this is 100% free-range ciphertext"
        else:
            ciphertext = self._crypto_power.encrypt_for(pubkey_sign_id, cleartext)

        if sign:
            if sign_cleartext:
                signature = self.seal(cleartext)
            else:
                signature = self.seal(ciphertext)
        else:
            signature = NOT_SIGNED

        return ciphertext, signature

    def verify_from(self, actor_whom_sender_claims_to_be: "Character", signature: bytes,
                    *messages: bytes, decrypt=False,
                    signature_is_on_cleartext=False,
                    cheat_cleartext=None) -> tuple:
        """
        Inverse of encrypt_for.

        :param actor_that_sender_claims_to_be: A Character instance representing the actor whom the sender claims to be.  We check the public key owned by this Character instance to verify.
        :param messages: The messages to be verified.
        :param decrypt: Whether or not to decrypt the messages.
        :param signature_is_on_cleartext: True if we expect the signature to be on the cleartext.  Otherwise, we presume that the ciphertext is what is signed.
        :return: (Whether or not the signature is valid, the decrypted plaintext or NO_DECRYPTION_PERFORMED)
        """
        cleartext = NO_DECRYPTION_PERFORMED
        if signature_is_on_cleartext:
            if decrypt:
                cleartext = self._crypto_power.decrypt(*messages)
                msg_digest = api.keccak_digest(cleartext)
            else:
                raise ValueError(
                    "Can't look for a signature on the cleartext if we're not decrypting.")
        else:
            msg_digest = b"".join(api.keccak_digest(m) for m in messages)

        # TODO: Remove this block once encrypting power is implemented.
        if cheat_cleartext:
            cleartext = cheat_cleartext
            msg_digest = api.keccak_digest(cleartext)

        actor = self._lookup_actor(actor_whom_sender_claims_to_be)
        signature_pub_key = actor.seal.as_tuple()  # TODO: and again, maybe in the real world this looks in KeyStore.

        sig = api.ecdsa_load_sig(signature)
        return api.ecdsa_verify(*sig, msg_digest, signature_pub_key), cleartext

    def _lookup_actor(self, actor: "Character"):
        try:
            return self._actor_mapping[actor.id()]
        except KeyError:
            raise self.NotFound("We haven't learned of an actor with ID {}".format(actor.id()))

    def id(self):
        return "whatever actor id ends up being - {}".format(id(self))


class Alice(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningKeypair]

    def find_best_ursula(self):
        # TODO: Right now this just finds the nearest node and returns its ip and port.  Make it do something useful.
        return self.server.bootstrappableNeighbors()[0]

    def generate_re_encryption_keys(self,
                                    pubkey_enc_bob,
                                    m,
                                    n):
        # TODO: Make this actually work.
        kfrags = [
            'sfasdfsd9',
            'dfasd09fi',
            'sdfksd3f9',
        ]

        return kfrags


class Bob(Character):
    _default_crypto_powerups = [SigningKeypair]


class Ursula(Character):
    _server_class = NuCypherDHTServer
    _default_crypto_powerups = [SigningKeypair]
