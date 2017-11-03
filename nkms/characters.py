import msgpack
from kademlia.network import Server
from kademlia.utils import digest

from nkms.crypto import api as API
from nkms.crypto.api import secure_random
from nkms.crypto.constants import NOT_SIGNED, NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningPower, EncryptingPower
from nkms.network.blockchain_client import list_all_ursulas
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer

import asyncio

from nkms.policy.constants import NOT_FROM_ALICE


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server
    _default_crypto_powerups = None
    _seal = None

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
        self._actor_mapping = {}
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

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
            __call__ = self._crypto_power.sign

            def _as_tuple(seal):
                return self._crypto_power.pubkey_sig_tuple()

            def __iter__(seal):
                yield from seal._as_tuple()

            def __bytes__(seal):
                return self._crypto_power.pubkey_sig_bytes()

            def __eq__(seal, other):
                return other == seal._as_tuple() or other == bytes(seal)

        self._seal = Seal()

        if attach_server:
            self.attach_server()

    def attach_server(self, ksize=20, alpha=3, id=None, storage=None,
                      *args, **kwargs) -> None:
        self._server = self._server_class(ksize, alpha, id, storage, *args, **kwargs)

    @property
    def seal(self):
        if not self._seal:
            raise AttributeError("Seal has not been set up yet.")
        else:
            return self._seal

    @property
    def server(self) -> Server:
        if self._server:
            return self._server
        else:
            raise RuntimeError("Server hasn't been attached.")

    @property
    def name(self):
        return self.__class__.__name__

    def learn_about_actor(self, actor):
        self._actor_mapping[actor.id()] = actor

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

        ciphertext = self._crypto_power.encrypt_for(actor.public_key(EncryptingPower),
                                                    cleartext)
        if sign:
            if sign_cleartext:
                signature = self.seal(cleartext)
            else:
                signature = self.seal(ciphertext)
        else:
            signature = NOT_SIGNED

        return ciphertext, signature

    def verify_from(self, actor_whom_sender_claims_to_be: "Character", signature: bytes,
                    message: bytes, decrypt=False,
                    signature_is_on_cleartext=False) -> tuple:
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
                cleartext = self._crypto_power.decrypt(message)
                msg_digest = API.keccak_digest(cleartext)
            else:
                raise ValueError(
                    "Can't look for a signature on the cleartext if we're not decrypting.")
        else:
            msg_digest = API.keccak_digest(message)

        actor = self._lookup_actor(actor_whom_sender_claims_to_be)
        signature_pub_key = actor.seal

        sig = API.ecdsa_load_sig(signature)
        return API.ecdsa_verify(*sig, msg_digest, signature_pub_key), cleartext

    def _lookup_actor(self, actor: "Character"):
        try:
            return self._actor_mapping[actor.id()]
        except KeyError:
            raise self.NotFound("We haven't learned of an actor with ID {}".format(actor.id()))

    def id(self):
        return "whatever actor id ends up being - {}".format(id(self))

    def public_key(self, key_class):
        try:
            return self._crypto_power.public_keys[key_class]
        except KeyError:
            raise  # TODO: Does it make sense to have a specialized exception here?  Probably.


class Alice(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def find_best_ursula(self):
        # TODO: This just finds *some* Ursula - let's have it find a particularly good one.
        return list_all_ursulas()[0]

    def generate_rekey_frags(self, alice_privkey, bob, m, n):
        """
        Generates re-encryption key frags and returns the frags and encrypted
        ephemeral key data.

        :param alice_privkey: Alice's private key
        :param bob_pubkey: Bob's public key
        :param m: Minimum number of rekey shares needed to rebuild ciphertext
        :param n: Total number of rekey shares to generate

        :return: Tuple(kfrags, eph_key_data)
        """
        kfrags, eph_key_data = API.ecies_ephemeral_split_rekey(
                                    alice_privkey, bytes(bob.seal), m, n)
        return (kfrags, eph_key_data)


class Bob(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, alice=None):
        super().__init__()
        if alice:
            self.alice = alice

    @property
    def alice(self):
        if not self._alice:
            raise Alice.NotFound
        else:
            return self._alice

    @alice.setter
    def alice(self, alice_object):
        self.learn_about_actor(alice_object)
        self._alice = alice_object

    def get_treasure_map(self, policy_group, signature):
        ursula_coro = self.server.get(policy_group.id)
        event_loop = asyncio.get_event_loop()
        packed_encrypted_treasure_map = event_loop.run_until_complete(ursula_coro)
        encrypted_treasure_map = msgpack.loads(packed_encrypted_treasure_map)
        verified, packed_node_list = self.verify_from(self.alice, signature, encrypted_treasure_map,
                                                  signature_is_on_cleartext=True, decrypt=True)
        if not verified:
            return NOT_FROM_ALICE
        else:
            from nkms.policy.models import TreasureMap
            return TreasureMap(msgpack.loads(packed_node_list))


class Ursula(Character):
    _server_class = NuCypherDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    port = None
    interface = None

    def ip_dht_key(self):
        return b"uaddr-" + bytes(self.seal)

    def attach_server(self, ksize=20, alpha=3, id=None, storage=None,
                      *args, **kwargs):

        if not id:
            id = digest(secure_random(32))  # TODO: Network-wide deterministic ID generation (ie, auction or whatever)

        super().attach_server(ksize, alpha, id, storage)

    def listen(self, port, interface):
        self.port = port
        self.interface = interface
        return self.server.listen(port, interface)

    def publish_interface_information(self):
        if not self.port and self.interface:
            raise RuntimeError("Must listen before publishing interface information.")
        setter = self.server.set(key=self.ip_dht_key(), value=msgpack.dumps((self.port, self.interface)))
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setter)


def community_meeting(*characters):
    for character in characters:
        for newcomer in characters:
            character.learn_about_actor(newcomer)
