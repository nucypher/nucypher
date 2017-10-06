from kademlia.network import Server
from nkms.crypto.constants import NOT_SIGNED
from nkms.crypto.keyring import KeyRing
from nkms.crypto.powers import CryptoPower, SigningKeypair
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server
    _actor_mapping = {}

    class ActorNotFound(Exception):
        """raised when we try to interact with an actor of whom we haven't learned yet."""

    def __init__(self, attach_server=True, crypto_power: CryptoPower=None):
        if attach_server:
            self.attach_server()
        self._crypto_power = crypto_power or CryptoPower(power_ups=[SigningKeypair])

        class Seal(object):
            """
            Can be called to sign something or used to express the signing public key as bytes.
            """
            def __call__(seal_instance, *messages_to_sign):
                return self._crypto_power.sign(*messages_to_sign)
            def as_bytes(seal_instance):
                return self._crypto_power.pubkey_sig_bytes()

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

    def learn_about_actor(self, actor_id, actor):
        self._actor_mapping[actor_id] = actor

    def encrypt_for(self, recipient: str, cleartext: bytes, sign: bool = True,
                    sign_cleartext=True) -> tuple:
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
        ciphertext = self._crypto_power.encrypt_for(pubkey_sign_id, cleartext)

        if sign:
            if sign_cleartext:
                signature = self.keyring.sign(cleartext)
            else:
                signature = self.keyring.sign(ciphertext)
        else:
            signature = NOT_SIGNED

        return ciphertext, signature

    def verify_from(self, actor_whom_sender_claims_to_be: str, signature: bytes,
                    ciphertext: bytes = None, decrypt=True,
                    signature_is_on_cleartext=True) -> tuple:
        """
        Inverse of encrypt_for.

        :param actor_that_sender_claims_to_be: The str representation of the actor on this KeyRing
            that the sender is claiming to be.
        :param ciphertext:
        :param decrypt:
        :param signature_is_on_cleartext:
        :return:
        """
        actor = self._lookup_actor(actor_whom_sender_claims_to_be)
        pubkey_sign_id = actor.pubkey_collection['signing']
        signature = self.keyring.sign()
        self.keyring.encrypt_for(pubkey_sign_id)

    def _lookup_actor(self, actor_id: str):
        try:
            return self._actor_mapping[actor_id]
        except KeyError:
            raise self.ActorNotFound("We haven't learned of an actor with ID {}".format(actor_id))


class Ursula(Character):
    _server_class = NuCypherDHTServer


class Alice(Character):
    _server_class = NuCypherSeedOnlyDHTServer

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
