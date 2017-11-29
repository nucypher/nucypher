import asyncio
import binascii
from binascii import hexlify
from logging import getLogger

import msgpack
from apistar import http
from apistar.core import Route
from apistar.frameworks.wsgi import WSGIApp as App
from sqlalchemy.exc import IntegrityError

from kademlia.network import Server
from kademlia.utils import digest
from nkms.crypto import api as API
from nkms.crypto.api import secure_random, keccak_digest
from nkms.crypto.constants import NOT_SIGNED, NO_DECRYPTION_PERFORMED
from nkms.crypto.powers import CryptoPower, SigningPower, EncryptingPower
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.keystore.keypairs import Keypair
from nkms.network import blockchain_client
from nkms.network.protocols import dht_value_splitter
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer
from nkms.policy.constants import NOT_FROM_ALICE


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server
    _default_crypto_powerups = None
    _seal = None

    def __init__(self, attach_server=True, crypto_power: CryptoPower = None,
                 crypto_power_ups=[], is_me=True) -> None:
        """
        :param attach_server:  Whether to attach a Server when this Character is born.
        :param crypto_power: A CryptoPower object; if provided, this will be the character's CryptoPower.
        :param crypto_power_ups:  If crypto_power is not provided, a new CryptoPower will be made and
            will consume all of the CryptoPowerUps in this list.

        If neither crypto_power nor crypto_power_ups are provided, we give this Character all CryptoPowerUps
        listed in their _default_crypto_powerups attribute.

        :param is_me: Set this to True when you want this Character to represent the owner of the configuration under
            which the program is being run.  A Character who is_me can do things that other Characters can't, like run
            servers, sign messages, and decrypt messages which are encrypted for them.  Typically this will be True
            for exactly one Character, but there are scenarios in which its imaginable to be represented by zero Characters
            or by more than one Character.
        """
        self.log = getLogger("characters")
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        if crypto_power:
            self._crypto_power = crypto_power
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(self._default_crypto_powerups)

        if is_me:
            self._actor_mapping = {}

            self._seal = Seal(self)

            if attach_server:
                self.attach_server()
        else:
            self._seal = StrangerSeal(self)

    class NotFound(KeyError):
        """raised when we try to interact with an actor of whom we haven't learned yet."""

    @classmethod
    def from_pubkey_sig_bytes(cls, pubkey_sig_bytes):
        return cls(is_me=False, crypto_power_ups=[SigningPower(keypair=Keypair.deserialize_key(pubkey_sig_bytes))])

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

    def hash(self, message):
        return keccak_digest(message)

    def learn_about_actor(self, actor):
        self._actor_mapping[actor.id()] = actor

    def encrypt_for(self, recipient: "Character", cleartext: bytes, sign: bool = True,
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

        if sign:
            if sign_cleartext:
                signature = self.seal(cleartext)
                ciphertext = self._crypto_power.encrypt_for(actor.public_key(EncryptingPower),
                                                            signature + cleartext)
            else:
                ciphertext = self._crypto_power.encrypt_for(actor.public_key(EncryptingPower),
                                                            cleartext)
                signature = self.seal(ciphertext)
        else:
            signature = NOT_SIGNED
            ciphertext = self._crypto_power.encrypt_for(actor.public_key(EncryptingPower),
                                                        cleartext)

        return ciphertext, signature

    def verify_from(self, actor_whom_sender_claims_to_be: "Character", message: bytes, signature: Signature = None,
                    decrypt=False,
                    signature_is_on_cleartext=False) -> tuple:
        """
        Inverse of encrypt_for.

        :param actor_that_sender_claims_to_be: A Character instance representing the actor whom the sender claims to be.  We check the public key owned by this Character instance to verify.
        :param messages: The messages to be verified.
        :param decrypt: Whether or not to decrypt the messages.
        :param signature_is_on_cleartext: True if we expect the signature to be on the cleartext.  Otherwise, we presume that the ciphertext is what is signed.
        :return: (Whether or not the signature is valid, the decrypted plaintext or NO_DECRYPTION_PERFORMED)
        """
        if not signature and not signature_is_on_cleartext:
            raise ValueError("You need to either provide the Signature or decrypt and find it on the cleartext.")

        cleartext = NO_DECRYPTION_PERFORMED

        if signature_is_on_cleartext:
            if decrypt:
                cleartext = self._crypto_power.decrypt(message)
                signature, message = BytestringSplitter(Signature)(cleartext, return_remainder=True)
            else:
                raise ValueError(
                    "Can't look for a signature on the cleartext if we're not decrypting.")

        actor = self._lookup_actor(actor_whom_sender_claims_to_be)

        return signature.verify(message, actor.seal), cleartext

    def _lookup_actor(self, actor: "Character"):
        try:
            return self._actor_mapping[actor.id()]
        except KeyError:
            raise self.NotFound("We haven't learned of an actor with ID {}".format(actor.id()))

    def id(self):
        return hexlify(bytes(self.seal))

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
        return list_all_ursulas()[1]

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
            alice_privkey, bytes(bob.seal.without_metabytes()), m, n)
        return (kfrags, eph_key_data)

    def publish_treasure_map(self, policy_group):
        encrypted_treasure_map, signature_for_bob = self.encrypt_for(policy_group.bob,
                                                                     policy_group.treasure_map.packed_payload())
        signature_for_ursula = self.seal(policy_group.hrac())  # TODO: Great use-case for Ciphertext class

        # In order to know this is safe to propagate, Ursula needs to see a signature, our public key,
        # and, reasons explained in treasure_map_dht_key above, the uri_hash.
        dht_value = signature_for_ursula + self.seal + policy_group.hrac() + msgpack.dumps(
            encrypted_treasure_map)  # TODO: Ideally, this is a Ciphertext object instead of msgpack (see #112)
        dht_key = policy_group.treasure_map_dht_key()

        setter = self.server.set(dht_key, b"trmap" + dht_value)
        return setter, encrypted_treasure_map, dht_value, signature_for_bob, signature_for_ursula


class Bob(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, alice=None):
        super().__init__()
        self._ursulas = {}
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

    def follow_treasure_map(self, treasure_map):
        # TODO: perform this part concurrently.
        for ursula_interface_id in treasure_map:
            getter = self.server.get(ursula_interface_id)
            loop = asyncio.get_event_loop()
            value = loop.run_until_complete(getter)
            signature, ursula_pubkey_sig, hrac, (port, interface, ttl) = dht_value_splitter(value.lstrip(b"uaddr"),
                                                                                            msgpack_remainder=True)

            # TODO: If we're going to implement TTL, it will be here.
            self._ursulas[ursula_interface_id] = Ursula.as_discovered_on_network(port=port, interface=interface,
                                                                                 pubkey_sig_bytes=ursula_pubkey_sig)

    def get_treasure_map(self, policy_group):

        dht_key = policy_group.treasure_map_dht_key()

        ursula_coro = self.server.get(dht_key)
        event_loop = asyncio.get_event_loop()
        packed_encrypted_treasure_map = event_loop.run_until_complete(ursula_coro)
        _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map = dht_value_splitter(
            packed_encrypted_treasure_map[5::], msgpack_remainder=True)
        verified, cleartext = self.verify_from(self.alice, encrypted_treasure_map,
                                                      signature_is_on_cleartext=True, decrypt=True)
        alices_signature, packed_node_list = BytestringSplitter(Signature)(cleartext, return_remainder=True)
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
    interface_ttl = 0

    def __init__(self, urulsas_keystore=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keystore = urulsas_keystore

        self._rest_app = None

    @property
    def rest_app(self):
        if not self._rest_app:
            raise AttributeError(
                "This Ursula doesn't have a REST app attached.  If you want one, init with is_me and attach_server.")
        else:
            return self._rest_app

    @staticmethod
    def as_discovered_on_network(port, interface, pubkey_sig_bytes):
        ursula = Ursula.from_pubkey_sig_bytes(pubkey_sig_bytes)
        ursula.port = port
        ursula.interface = interface
        return ursula

    def attach_server(self, ksize=20, alpha=3, id=None, storage=None,
                      *args, **kwargs):

        if not id:
            id = digest(secure_random(32))  # TODO: Network-wide deterministic ID generation (ie, auction or whatever)

        super().attach_server(ksize, alpha, id, storage)

        routes = [
            Route('/kFrag/{hrac_as_hex}', 'POST', self.set_policy),
        ]

        self._rest_app = App(routes=routes)

    def listen(self, port, interface):
        self.port = port
        self.interface = interface
        return self.server.listen(port, interface)

    def interface_info(self):
        return self.port, self.interface, self.interface_ttl

    def interface_dht_key(self):
        return self.hash(self.seal + self.interface_hrac())

    def interface_dht_value(self):
        signature = self.seal(self.interface_hrac())
        return b"uaddr" + signature + self.seal + self.interface_hrac() + msgpack.dumps(self.interface_info())

    def interface_hrac(self):
        return self.hash(msgpack.dumps(self.interface_info()))

    def publish_interface_information(self):
        if not self.port and self.interface:
            raise RuntimeError("Must listen before publishing interface information.")

        dht_key = self.interface_dht_key()
        value = self.interface_dht_value()
        setter = self.server.set(key=dht_key, value=value)
        blockchain_client._ursulas_on_blockchain.append(dht_key)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setter)

    def set_policy(self, hrac_as_hex, request: http.Request):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved Policy (see #121).
        """
        from nkms.policy.models import Policy  # Avoid circular import
        hrac = binascii.unhexlify(hrac_as_hex)
        policy = Policy.from_ursula(request.body, self)

        try:
            self.keystore.add_kfrag(hrac, policy.kfrag, policy.alices_signature)
        except IntegrityError:
            raise
            # Do something appropriately RESTful (ie, 4xx).

        return  # A 200, which whatever policy metadata.


class Seal(object):
    """
    Can be called to sign something or used to express the signing public key as bytes.
    """

    def __init__(self, character):
        self.character = character

    def __call__(self, *args, **kwargs):
        return self.character._crypto_power.sign(*args, **kwargs)

    def _as_tuple(self):
        return self.character._crypto_power.pubkey_sig_tuple()

    def __iter__(seal):
        yield from seal._as_tuple()

    def __bytes__(self):
        return self.character._crypto_power.pubkey_sig_bytes()

    def __eq__(self, other):
        return other == self._as_tuple() or other == bytes(self)

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __len__(self):
        return len(bytes(self))

    def without_metabytes(self):
        return self.character._crypto_power.pubkey_sig_bytes().without_metabytes()


class StrangerSeal(Seal):
    """
    Seal of a stranger (ie, can only be used to glean public key, not to sign)
    """

    def __call__(self, *args, **kwargs):
        raise TypeError(
            "This isn't your Seal; it belongs to {} (a Stranger).  You can't sign with it.".format(self.character))


def congregate(*characters):
    for character in characters:
        for newcomer in characters:
            character.learn_about_actor(newcomer)
