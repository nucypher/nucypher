import asyncio
from logging import getLogger

import msgpack
import requests
from collections import OrderedDict
from kademlia.network import Server
from kademlia.utils import digest
from typing import Dict
from typing import Union, List

from nkms.crypto.api import secure_random, keccak_digest
from nkms.crypto.constants import NOT_SIGNED, NO_DECRYPTION_PERFORMED, PUBLIC_KEY_LENGTH
from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import CryptoPower, SigningPower, EncryptingPower
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter, RepeatingBytestringSplitter
from nkms.network import blockchain_client
from nkms.network.constants import BYTESTRING_IS_URSULA_IFACE_INFO
from nkms.network.protocols import dht_value_splitter
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer, ProxyRESTServer
from nkms.policy.constants import NOT_FROM_ALICE, NON_PAYMENT

from nkms_eth.actors import PolicyAuthor

from umbral import pre
from umbral.keys import UmbralPublicKey


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server
    _default_crypto_powerups = None
    _stamp = None

    def __init__(self, attach_server=True, crypto_power: CryptoPower = None,
                 crypto_power_ups=[], is_me=True) -> None:
        """
        :param attach_server:  Whether to attach a Server when this Character is
            born.
        :param crypto_power: A CryptoPower object; if provided, this will be the
            character's CryptoPower.
        :param crypto_power_ups:  If crypto_power is not provided, a new
            CryptoPower will be made and will consume all of the CryptoPowerUps
            in this list.

        If neither crypto_power nor crypto_power_ups are provided, we give this
        Character all CryptoPowerUps listed in their _default_crypto_powerups
        attribute.

        :param is_me: Set this to True when you want this Character to represent
            the owner of the configuration under which the program is being run.
            A Character who is_me can do things that other Characters can't,
            like run servers, sign messages, and decrypt messages which are
            encrypted for them.  Typically this will be True for exactly one
            Character, but there are scenarios in which its imaginable to be
            represented by zero Characters or by more than one Character.
        """
        self.known_nodes = {}
        self.log = getLogger("characters")
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        if is_me:
            self._stamp = SignatureStamp(self)

            if attach_server:
                self.attach_server()
        else:
            self._stamp = StrangerStamp(self)

        if crypto_power:
            self._crypto_power = crypto_power
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups,
                                             generate_keys_if_needed=is_me)
        else:
            self._crypto_power = CryptoPower(self._default_crypto_powerups,
                                             generate_keys_if_needed=is_me)

    def __eq__(self, other):
        return bytes(self.stamp) == bytes(other.stamp)

    def __hash__(self):
        return int.from_bytes(self.stamp, byteorder="big")

    class NotEnoughUrsulas(RuntimeError):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class SuspiciousActivity(RuntimeError):
        """raised when an action appears to amount to malicious conduct."""

    @classmethod
    def from_public_keys(cls, powers_and_keys: Dict, *args, **kwargs):
        """
        Sometimes we discover a Character and, at the same moment, learn one or
        more of their public keys. Here, we take a Dict
        (powers_and_key_bytes) in the following format:
        {CryptoPowerUp class: public_key_bytes}

        Each item in the collection will have the CryptoPowerUp instantiated
        with the public_key_bytes, and the resulting CryptoPowerUp instance
        consumed by the Character.
        """
        crypto_power = CryptoPower()

        for power_up, public_key in powers_and_keys.items():
            try:
                umbral_key = UmbralPublicKey(public_key)
            except TypeError:
                umbral_key = public_key

            crypto_power.consume_power_up(power_up(pubkey=umbral_key))

        return cls(is_me=False, crypto_power=crypto_power, *args, **kwargs)

    def attach_server(self, ksize=20, alpha=3, id=None,
                      storage=None, *args, **kwargs) -> None:
        if self._server:
            raise RuntimeError("Attaching the server twice is almost certainly a bad idea.")
        self._server = self._server_class(
            ksize, alpha, id, storage, *args, **kwargs)

    @property
    def stamp(self):
        if not self._stamp:
            raise AttributeError("SignatureStamp has not been set up yet.")
        else:
            return self._stamp

    @property
    def server(self) -> Server:
        if self._server:
            return self._server
        else:
            raise RuntimeError("Server hasn't been attached.")

    @property
    def name(self):
        return self.__class__.__name__

    def encrypt_for(self,
                    recipient: "Character",
                    plaintext: bytes,
                    sign: bool=True,
                    sign_plaintext=True,
                    ) -> tuple:
        """
        Encrypts plaintext for recipient actor. Optionally signs the message as well.

        :param recipient: The character whose public key will be used to encrypt
            cleartext.
        :param plaintext: The secret to be encrypted.
        :param sign: Whether or not to sign the message.
        :param sign_plaintext: When signing, the cleartext is signed if this is
            True,  Otherwise, the resulting ciphertext is signed.

        :return: A tuple, (ciphertext, signature).  If sign==False,
            then signature will be NOT_SIGNED.
        """
        recipient_pubkey_enc = recipient.public_key(EncryptingPower)
        if sign:
            if sign_plaintext:
                # Sign first, encrypt second.
                signature = self.stamp(plaintext)
                ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, signature + plaintext)
            else:
                # Encrypt first, sign second.
                ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, plaintext)
                signature = self.stamp(ciphertext)
            alice_pubkey = self.public_key(SigningPower)
        else:
            # Don't sign.
            signature = NOT_SIGNED
            ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, plaintext)
            alice_pubkey = None

        message_kit = MessageKit(ciphertext=ciphertext, capsule=capsule, alice_pubkey=alice_pubkey)

        return message_kit, signature

    def verify_from(self,
                    actor_whom_sender_claims_to_be: "Character",
                    message_kit: Union[MessageKit, bytes],
                    signature: Signature=None,
                    decrypt=False,
                    signature_is_on_cleartext=False) -> tuple:
        """
        Inverse of encrypt_for.

        :param actor_that_sender_claims_to_be: A Character instance representing
            the actor whom the sender claims to be.  We check the public key
            owned by this Character instance to verify.
        :param messages: The messages to be verified.
        :param decrypt: Whether or not to decrypt the messages.
        :param signature_is_on_cleartext: True if we expect the signature to be
            on the cleartext. Otherwise, we presume that the ciphertext is what
            is signed.
        :return: Whether or not the signature is valid, the decrypted plaintext
            or NO_DECRYPTION_PERFORMED
        """
        # TODO: In this flow we now essentially have two copies of the public key.  See #174.
        # One from the actor (first arg) and one from the MessageKit.
        # Which do we use in which cases?

        # if not signature and not signature_is_on_cleartext:
        # TODO: Since a signature can now be in a MessageKit, this might not be accurate anymore.  See #174.
        # raise ValueError("You need to either provide the Signature or \
        #                   decrypt and find it on the cleartext.")

        cleartext = NO_DECRYPTION_PERFORMED

        if signature_is_on_cleartext:
            if decrypt:
                cleartext_with_sig = self.decrypt(message_kit)
                signature, cleartext = BytestringSplitter(Signature)(cleartext_with_sig,
                                                                     return_remainder=True)
                message_kit.signature = signature  # TODO: Obviously this is the wrong way to do this.  Let's make signature a property.
            else:
                raise ValueError(
                    "Can't look for a signature on the cleartext if we're not \
                     decrypting.")
            message = cleartext
            alice_pubkey = message_kit.alice_pubkey
        else:
            # The signature is on the ciphertext.  We might not even need to decrypt it.
            if decrypt:
                message = message_kit.ciphertext
                cleartext = self.decrypt(message_kit)
            else:
                message = bytes(message_kit)
            alice_pubkey = actor_whom_sender_claims_to_be.public_key(SigningPower)

        if signature:
            is_valid = signature.verify(message, alice_pubkey)
        else:
            # Meh, we didn't even get a signature.  Not much we can do.
            is_valid = False

        return is_valid, cleartext

    """
    Next we have decrypt(), sign(), and generate_self_signed_certificate() - these use the private 
    keys of their respective powers; any character who has these powers can use these functions.

    If they don't have the correct Power, the appropriate PowerUpError is raised.
    """

    def decrypt(self, message_kit):
        return self._crypto_power.power_ups(EncryptingPower).decrypt(message_kit)

    def sign(self, message):
        return self._crypto_power.power_ups(SigningPower).sign(message)

    def generate_self_signed_certificate(self):
        signing_power = self._crypto_power.power_ups(SigningPower)
        return signing_power.generate_self_signed_cert(self.stamp.fingerprint().decode())

    """
    And finally, some miscellaneous but generally-applicable abilities:
    """

    def public_key(self, power_up_class):
        """
        Pass a power_up_class, get the public key for this Character which corresponds to that
        class.

        If the Character doesn't have the power corresponding to that class, raises the
        appropriate PowerUpError (ie, NoSigningPower or NoEncryptingPower).
        """
        power_up = self._crypto_power.power_ups(power_up_class)
        return power_up.public_key()

    def learn_about_nodes(self, address, port):
        """
        Sends a request to node_url to find out about known nodes.
        """
        # TODO: Find out about other known nodes, not just this one.  #175
        node = Ursula.from_rest_url(address, port)
        self.known_nodes[node.interface_dht_key()] = node


class Alice(Character, PolicyAuthor):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def generate_kfrags(self, bob, m, n) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.
        :param bob: Bob instance which will be able to decrypt messages re-encrypted with these kfrags.
        :param m: Minimum number of kfrags needed to activate a Capsule.
        :param n: Total number of kfrags to generate
        """
        bob_pubkey_enc = bob.public_key(EncryptingPower)
        return self._crypto_power.power_ups(EncryptingPower).generate_kfrags(bob_pubkey_enc, m, n)

    def create_policy(self, bob: "Bob", uri: bytes, m: int, n: int):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """
        kfrags = self.generate_kfrags(bob, m, n)
        from nkms.policy.models import Policy
        policy = Policy.from_alice(
            alice=self,
            bob=bob,
            kfrags=kfrags,
            uri=uri,
            m=m,
        )

        return policy

    def grant(self, bob, uri, networky_stuff,
              m=None, n=None, expiration=None, deposit=None):
        if not m:
            # TODO: get m from config  #176
            raise NotImplementedError
        if not n:
            # TODO: get n from config  #176
            raise NotImplementedError
        if not expiration:
            # TODO: check default duration in config  #176
            raise NotImplementedError
        if not deposit:
            default_deposit = None  # TODO: Check default deposit in config.  #176
            if not default_deposit:
                deposit = networky_stuff.get_competitive_rate()
                if deposit == NotImplemented:
                    deposit = NON_PAYMENT

        policy = self.create_policy(bob, uri, m, n)

        # We'll find n Ursulas by default.  It's possible to "play the field"
        # by trying differet
        # deposits and expirations on a limited number of Ursulas.
        # Users may decide to inject some market strategies here.
        found_ursulas = policy.find_ursulas(networky_stuff, deposit,
                                            expiration, num_ursulas=n)
        policy.match_kfrags_to_found_ursulas(found_ursulas)
        # REST call happens here, as does population of TreasureMap.
        policy.enact(networky_stuff)

        return policy  # Now with TreasureMap affixed!


class Bob(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.treasure_maps = {}

        from nkms.policy.models import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
        self._saved_work_orders = WorkOrderHistory()

    def follow_treasure_map(self, hrac):
        for ursula_interface_id in self.treasure_maps[hrac]:
            if ursula_interface_id in self.known_nodes:
                # If we already know about this Ursula,
                # we needn't learn about it again.
                continue

            # TODO: perform this part concurrently.
            value = self.server.get_now(ursula_interface_id)

            # TODO: Make this much prettier
            header, signature, ursula_pubkey_sig, _hrac, (
            port, interface, ttl) = dht_value_splitter(value, msgpack_remainder=True)

            if header != BYTESTRING_IS_URSULA_IFACE_INFO:
                raise TypeError("Unknown DHT value.  How did this get on the network?")

            # TODO: If we're going to implement TTL, it will be here.
            self.known_nodes[ursula_interface_id] = \
                Ursula.as_discovered_on_network(
                    dht_port=port,
                    dht_interface=interface,
                    powers_and_keys=({SigningPower: ursula_pubkey_sig})
                )

    def get_treasure_map(self, policy, networky_stuff, using_dht=False):
        map_id = policy.treasure_map_dht_key()

        if using_dht:
            ursula_coro = self.server.get(map_id)
            event_loop = asyncio.get_event_loop()
            packed_encrypted_treasure_map = event_loop.run_until_complete(ursula_coro)
        else:
            if not self.known_nodes:
                # TODO: Try to find more Ursulas on the blockchain.
                raise self.NotEnoughUrsulas
            tmap_message_kit = self.get_treasure_map_from_known_ursulas(networky_stuff, map_id)

        verified, packed_node_list = self.verify_from(
            policy.alice, tmap_message_kit,
            signature_is_on_cleartext=True, decrypt=True
        )

        if not verified:
            return NOT_FROM_ALICE
        else:
            from nkms.policy.models import TreasureMap
            treasure_map = TreasureMap(msgpack.loads(packed_node_list))
            self.treasure_maps[policy.hrac()] = treasure_map
            return treasure_map

    def get_treasure_map_from_known_ursulas(self, networky_stuff, map_id):
        """
        Iterate through swarm, asking for the TreasureMap.
        Return the first one who has it.
        TODO: What if a node gives a bunk TreasureMap?
        """
        from nkms.network.protocols import dht_value_splitter
        for node in self.known_nodes.values():
            response = networky_stuff.get_treasure_map_from_node(node, map_id)

            if response.status_code == 200 and response.content:
                # TODO: Make this prettier
                header, _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map = \
                    dht_value_splitter(response.content, return_remainder=True)
                tmap_messaage_kit = MessageKit.from_bytes(encrypted_treasure_map)
                return tmap_messaage_kit
            else:
                assert False

    def generate_work_orders(self, kfrag_hrac, *capsules, num_ursulas=None):
        from nkms.policy.models import WorkOrder  # Prevent circular import

        try:
            treasure_map_to_use = self.treasure_maps[kfrag_hrac]
        except KeyError:
            raise KeyError(
                "Bob doesn't have a TreasureMap matching the hrac {}".format(kfrag_hrac))

        generated_work_orders = OrderedDict()

        if not treasure_map_to_use:
            raise ValueError(
                "Bob doesn't have a TreasureMap to match any of these capsules: {}".format(
                    capsules))

        for ursula_dht_key in treasure_map_to_use:
            ursula = self.known_nodes[ursula_dht_key]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[ursula_dht_key]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    kfrag_hrac, capsules_to_include, ursula, self)
                generated_work_orders[ursula_dht_key] = work_order
                self._saved_work_orders[ursula_dht_key][capsule] = work_order

            if num_ursulas is not None:
                if num_ursulas == len(generated_work_orders):
                    break

        return generated_work_orders

    def get_reencrypted_c_frags(self, networky_stuff, work_order):
        cfrags = networky_stuff.reencrypt(work_order)
        if not len(work_order) == len(cfrags):
            raise ValueError("Ursula gave back the wrong number of cfrags.  She's up to something.")
        for counter, capsule in enumerate(work_order.capsules):
            # TODO: Ursula is actually supposed to sign this.  See #141.
            # TODO: Maybe just update the work order here instead of setting it anew.
            work_orders_by_ursula = self._saved_work_orders[bytes(work_order.ursula.stamp)]
            work_orders_by_ursula[capsule] = work_order
        return cfrags

    def get_ursula(self, ursula_id):
        return self._ursulas[ursula_id]


class Ursula(Character, ProxyRESTServer):
    _server_class = NuCypherDHTServer
    _alice_class = Alice
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, dht_port=None, dht_interface=None, dht_ttl=0,
                 rest_address=None, rest_port=None, db_name=None,
                 *args, **kwargs):
        self.dht_port = dht_port
        self.dht_interface = dht_interface
        self.dht_ttl = 0
        self._work_orders = []
        ProxyRESTServer.__init__(self, rest_address, rest_port, db_name)
        super().__init__(*args, **kwargs)

    @property
    def rest_app(self):
        if not self._rest_app:
            raise AttributeError(
                "This Ursula doesn't have a REST app attached.  If you want one, init with is_me and attach_server.")
        else:
            return self._rest_app

    @classmethod
    def as_discovered_on_network(cls, dht_port, dht_interface,
                                 rest_address=None, rest_port=None,
                                 powers_and_keys=()):
        # TODO: We also need the encrypting public key here.
        ursula = cls.from_public_keys(powers_and_keys)
        ursula.dht_port = dht_port
        ursula.dht_interface = dht_interface
        ursula.rest_address = rest_address
        ursula.rest_port = rest_port
        return ursula

    @classmethod
    def from_rest_url(cls, address, port):
        response = requests.get("{}:{}/public_keys".format(address, port), verify=False)  # TODO: TLS-only.
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))

        key_splitter = RepeatingBytestringSplitter(
            (UmbralPublicKey, PUBLIC_KEY_LENGTH, {"as_b64": False}))
        signing_key, encrypting_key = key_splitter(response.content)

        stranger_ursula_from_public_keys = cls.from_public_keys(
            {SigningPower: signing_key, EncryptingPower: encrypting_key},
            rest_address=address,
            rest_port=port
        )

        return stranger_ursula_from_public_keys

    def attach_server(self, ksize=20, alpha=3, id=None,
                      storage=None, *args, **kwargs):
        # TODO: Network-wide deterministic ID generation (ie, auction or
        # whatever)  See #136.
        if not id:
            id = digest(secure_random(32))

        super().attach_server(ksize, alpha, id, storage)
        self.attach_rest_server(db_name=self.db_name)

    def listen(self):
        return self.server.listen(self.dht_port, self.dht_interface)

    def dht_interface_info(self):
        return self.dht_port, self.dht_interface, self.dht_ttl

    def interface_dht_key(self):
        return bytes(self.stamp)
        # return self.InterfaceDHTKey(self.stamp, self.interface_hrac())

    def interface_dht_value(self):
        signature = self.stamp(self.interface_hrac())
        return (
            BYTESTRING_IS_URSULA_IFACE_INFO + signature + self.stamp + self.interface_hrac()
            + msgpack.dumps(self.dht_interface_info())
        )

    def interface_hrac(self):
        return keccak_digest(msgpack.dumps(self.dht_interface_info()))

    def publish_dht_information(self):
        if not self.dht_port and self.dht_interface:
            raise RuntimeError("Must listen before publishing interface information.")

        dht_key = self.interface_dht_key()
        value = self.interface_dht_value()
        setter = self.server.set(key=dht_key, value=value)
        blockchain_client._ursulas_on_blockchain.append(dht_key)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setter)

    def work_orders(self, bob=None):
        """
        TODO: This is better written as a model method for Ursula's datastore.
        """
        if not bob:
            return self._work_orders
        else:
            work_orders_from_bob = []
            for work_order in self._work_orders:
                if work_order.bob == bob:
                    work_orders_from_bob.append(work_order)
            return work_orders_from_bob


class SignatureStamp(object):
    """
    Can be called to sign something or used to express the signing public
    key as bytes.
    """

    def __init__(self, character):
        self.character = character

    def __call__(self, *args, **kwargs):
        return self.character.sign(*args, **kwargs)

    def __bytes__(self):
        return bytes(self.character.public_key(SigningPower))

    def __hash__(self):
        return int.from_bytes(self, byteorder="big")

    def __eq__(self, other):
        return other == bytes(self)

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __len__(self):
        return len(bytes(self))

    def as_umbral_pubkey(self):
        return self.character.public_key(SigningPower)

    def fingerprint(self):
        """
        Hashes the key using keccak-256 and returns the hexdigest in bytes.

        :return: Hexdigest fingerprint of key (keccak-256) in bytes
        """
        return keccak_digest(bytes(self)).hex().encode()


class StrangerStamp(SignatureStamp):
    """
    SignatureStamp of a stranger (ie, can only be used to glean public key, not to sign)
    """

    def __call__(self, *args, **kwargs):
        message = "This isn't your SignatureStamp; it belongs to {} (a Stranger).  You can't sign with it."
        raise TypeError(message.format(self.character))
