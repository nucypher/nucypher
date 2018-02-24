import asyncio
import binascii
from binascii import hexlify
from logging import getLogger
from typing import Union, List

import msgpack
import requests
from apistar import http
from apistar.core import Route
from apistar.frameworks.wsgi import WSGIApp as App
from apistar.http import Response
from kademlia.network import Server
from kademlia.utils import digest
from sqlalchemy.exc import IntegrityError

from nkms.crypto.api import secure_random, keccak_digest
from nkms.crypto.constants import NOT_SIGNED, NO_DECRYPTION_PERFORMED
from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import CryptoPower, SigningPower, EncryptingPower
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.network import blockchain_client
from nkms.network.constants import BYTESTRING_IS_URSULA_IFACE_INFO, BYTESTRING_IS_TREASURE_MAP
from nkms.network.protocols import dht_value_splitter
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer
from nkms.policy.constants import NOT_FROM_ALICE, NON_PAYMENT
from umbral import pre
from umbral.fragments import KFrag
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
        self.log = getLogger("characters")
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        if is_me:
            self._actor_mapping = {}

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

    class NotFound(KeyError):
        """raised when we try to interact with an actor of whom we haven't \
           learned yet."""

    class SuspiciousActivity(RuntimeError):
        """raised when an action appears to amount to malicious conduct."""

    @classmethod
    def from_public_keys(cls, *powers_and_keys):
        """
        Sometimes we discover a Character and, at the same moment, learn one or
        more of their public keys. Here, we take a collection of tuples
        (powers_and_key_bytes) in the following format:
        (CryptoPowerUp class, public_key_bytes)

        Each item in the collection will have the CryptoPowerUp instantiated
        with the public_key_bytes, and the resulting CryptoPowerUp instance
        consumed by the Character.
        """
        crypto_power = CryptoPower()

        for power_up, public_key in powers_and_keys:
            try:
                umbral_key = UmbralPublicKey(public_key)
            except TypeError:
                umbral_key = public_key

            crypto_power.consume_power_up(power_up(pubkey=umbral_key))

        return cls(is_me=False, crypto_power=crypto_power)

    def attach_server(self, ksize=20, alpha=3, id=None,
                      storage=None, *args, **kwargs) -> None:
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

    @staticmethod
    def hash(message):
        return keccak_digest(message)

    def learn_about_actor(self, actor):
        self._actor_mapping[actor.id()] = actor

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
        else:
            # Don't sign.
            signature = NOT_SIGNED
            ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, plaintext)


        message_kit = MessageKit(ciphertext=ciphertext, capsule=capsule)
        message_kit.alice_pubkey = self.public_key(SigningPower)
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
        # TODO: In this flow we now essentially have two copies of the public key.
        # One from the actor (first arg) and one from the MessageKit.
        # Which do we use in which cases?

        # if not signature and not signature_is_on_cleartext:
        # TODO: Since a signature can now be in a MessageKit, this might not be accurate anymore.
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
                # TODO: Fully deprecate actor lookup flow?
            else:
                message = bytes(message_kit)
            alice_pubkey = actor_whom_sender_claims_to_be.public_key(SigningPower)

        if signature:
            is_valid = signature.verify(message, alice_pubkey)
        else:
            # Meh, we didn't even get a signature.  Not much we can do.
            is_valid = False

        return is_valid, cleartext

    def decrypt(self, message_kit):
        return self._crypto_power.decrypt(message_kit)

    def _lookup_actor(self, actor: "Character"):
        try:
            return self._actor_mapping[actor.id()]
        except KeyError:
            raise self.NotFound(
                "We haven't learned of an actor with ID {}".format(actor.id()))

    def id(self):
        return hexlify(bytes(self.stamp))

    def public_key(self, key_class):
        # TODO: Does it make sense to have a specialized exception here? Probably.
        return self._crypto_power.public_keys[key_class]


class Alice(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def generate_kfrags(self, bob, m, n) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.

        :param bob: Bob's public key
        :param m: Minimum number of KFrags needed to rebuild ciphertext
        :param n: Total number of rekey shares to generate
        """
        bob_pubkey_enc = bob.public_key(EncryptingPower)

        return self._crypto_power.generate_kfrags(bob_pubkey_enc, m, n)

    def create_policy(self,
                      bob: "Bob",
                      uri: bytes,
                      m: int,
                      n: int,
                      ):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """
        kfrags = self.generate_kfrags(bob, m, n)
        # TODO: Access Alice's private key inside this method.
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
            # TODO: get m from config
            raise NotImplementedError
        if not n:
            # TODO: get n from config
            raise NotImplementedError
        if not expiration:
            # TODO: check default duration in config
            raise NotImplementedError
        if not deposit:
            default_deposit = None  # TODO: Check default deposit in config.
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

        return policy


class Bob(Character):
    _server_class = NuCypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, alice=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ursulas = {}
        self.treasure_maps = {}
        if alice:
            self.alice = alice
        from nkms.policy.models import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
        self._saved_work_orders = WorkOrderHistory()

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

    def follow_treasure_map(self, hrac):
        for ursula_interface_id in self.treasure_maps[hrac]:
            # TODO: perform this part concurrently.
            value = self.server.get_now(ursula_interface_id)

            # TODO: Make this much prettier
            header, signature, ursula_pubkey_sig, _hrac, (port, interface, ttl) = dht_value_splitter(value, msgpack_remainder=True)

            if header != BYTESTRING_IS_URSULA_IFACE_INFO:
                raise TypeError("Unknown DHT value.  How did this get on the network?")

            # TODO: If we're going to implement TTL, it will be here.
            self._ursulas[ursula_interface_id] =\
                    Ursula.as_discovered_on_network(
                            dht_port=port,
                            dht_interface=interface,
                            pubkey_sig_bytes=ursula_pubkey_sig
                    )

    def get_treasure_map(self, policy_group):

        dht_key = policy_group.treasure_map_dht_key()

        ursula_coro = self.server.get(dht_key)
        event_loop = asyncio.get_event_loop()
        packed_encrypted_treasure_map = event_loop.run_until_complete(ursula_coro)
        
        # TODO: Make this prettier
        header, _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map =\
        dht_value_splitter(packed_encrypted_treasure_map, return_remainder=True)
        tmap_messaage_kit = MessageKit.from_bytes(encrypted_treasure_map)

        if header != BYTESTRING_IS_TREASURE_MAP:
            raise TypeError("Unknown DHT value.  How did this get on the network?")

        verified, packed_node_list = self.verify_from(
            self.alice, tmap_messaage_kit,
            signature_is_on_cleartext=True, decrypt=True
        )

        if not verified:
            return NOT_FROM_ALICE
        else:
            from nkms.policy.models import TreasureMap
            self.treasure_maps[policy_group.hrac] = TreasureMap(
                msgpack.loads(packed_node_list)
            )
            return self.treasure_maps[policy_group.hrac]

    def generate_work_orders(self, kfrag_hrac, *capsules, num_ursulas=None):
        from nkms.policy.models import WorkOrder  # Prevent circular import

        try:
            treasure_map_to_use = self.treasure_maps[kfrag_hrac]
        except KeyError:
            raise KeyError(
                "Bob doesn't have a TreasureMap matching the hrac {}".format(kfrag_hrac))

        generated_work_orders = {}

        if not treasure_map_to_use:
            raise ValueError(
                "Bob doesn't have a TreasureMap to match any of these capsules: {}".format(
                    capsules))

        for ursula_dht_key in treasure_map_to_use:
            ursula = self._ursulas[ursula_dht_key]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[ursula_dht_key]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    kfrag_hrac, capsules_to_include, ursula_dht_key, self)
                generated_work_orders[ursula_dht_key] = work_order
                self._saved_work_orders[work_order.ursula_id][capsule] = work_order

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
            work_orders_by_ursula = self._saved_work_orders[work_order.ursula_id]
            work_orders_by_ursula[capsule] = work_order
        return cfrags

    def get_ursula(self, ursula_id):
        return self._ursulas[ursula_id]


class Ursula(Character):
    _server_class = NuCypherDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    dht_port = None
    dht_interface = None
    dht_ttl = 0
    rest_address = None
    rest_port = None

    def __init__(self, urulsas_keystore=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keystore = urulsas_keystore

        self._rest_app = None
        self._work_orders = []

    @property
    def rest_app(self):
        if not self._rest_app:
            raise AttributeError(
                "This Ursula doesn't have a REST app attached.  If you want one, init with is_me and attach_server.")
        else:
            return self._rest_app

    @classmethod
    def as_discovered_on_network(cls, dht_port, dht_interface, pubkey_sig_bytes,
                                 rest_address=None, rest_port=None):
        # TODO: We also need the encrypting public key here.
        ursula = cls.from_public_keys((SigningPower, pubkey_sig_bytes))
        ursula.dht_port = dht_port
        ursula.dht_interface = dht_interface
        ursula.rest_address = rest_address
        ursula.rest_port = rest_port
        return ursula

    @classmethod
    def from_rest_url(cls, url):
        response = requests.get(url)
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))
        signing_key_bytes, encrypting_key_bytes = \
            BytestringSplitter(PublicKey)(response.content,
                                          return_remainder=True)
        stranger_ursula_from_public_keys = cls.from_public_keys(
            signing=signing_key_bytes, encrypting=encrypting_key_bytes)
        return stranger_ursula_from_public_keys

    def attach_server(self, ksize=20, alpha=3, id=None,
                      storage=None, *args, **kwargs):
        # TODO: Network-wide deterministic ID generation (ie, auction or
        # whatever)  See #136.
        if not id:
            id = digest(secure_random(32))

        super().attach_server(ksize, alpha, id, storage)

        routes = [
            Route('/kFrag/{hrac_as_hex}',
                  'POST',
                  self.set_policy),
            Route('/kFrag/{hrac_as_hex}/reencrypt',
                  'POST',
                  self.reencrypt_via_rest),
            Route('/public_keys', 'GET',
                  self.get_signing_and_encrypting_public_keys),
            Route('/consider_contract',
                  'POST',
                  self.consider_contract),
        ]

        self._rest_app = App(routes=routes)

    def listen(self, port, interface):
        self.dht_port = port
        self.dht_interface = interface
        return self.server.listen(port, interface)

    def dht_interface_info(self):
        return self.dht_port, self.dht_interface, self.dht_ttl

    class InterfaceDHTKey:
        def __init__(self, stamp, interface_hrac):
            self.pubkey_sig_bytes = bytes(stamp)
            self.interface_hrac = interface_hrac

        def __bytes__(self):
            return Ursula.hash(self.pubkey_sig_bytes + self.interface_hrac)

        def __add__(self, other):
            return bytes(self) + other

        def __radd__(self, other):
            return other + bytes(self)

        def __hash__(self):
            return int.from_bytes(self, byteorder="big")

        def __eq__(self, other):
            return bytes(self) == bytes(other)

    def interface_dht_key(self):
        return self.InterfaceDHTKey(self.stamp, self.interface_hrac())

    def interface_dht_value(self):
        signature = self.stamp(self.interface_hrac())
        return (
            BYTESTRING_IS_URSULA_IFACE_INFO + signature + self.stamp + self.interface_hrac()
            + msgpack.dumps(self.dht_interface_info())
        )

    def interface_hrac(self):
        return self.hash(msgpack.dumps(self.dht_interface_info()))

    def publish_dht_information(self):
        if not self.dht_port and self.dht_interface:
            raise RuntimeError("Must listen before publishing interface information.")

        dht_key = self.interface_dht_key()
        value = self.interface_dht_value()
        setter = self.server.set(key=dht_key, value=value)
        blockchain_client._ursulas_on_blockchain.append(dht_key)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setter)

    def get_signing_and_encrypting_public_keys(self):
        """
        REST endpoint for getting both signing and encrypting public keys.
        """
        return Response(
            content=bytes(self.stamp) + bytes(self.public_key(EncryptingPower)),
            content_type="application/octet-stream")

    def consider_contract(self, hrac_as_hex, request: http.Request):
        # TODO: This actually needs to be a REST endpoint, with the payload
        # carrying the kfrag hash separately.
        from nkms.policy.models import Contract
        contract, deposit_as_bytes = \
            BytestringSplitter(Contract)(request.body, return_remainder=True)
        contract.deposit = deposit_as_bytes

        # contract_to_store = {  # TODO: This needs to be a datastore - see #127.
        #     "alice_pubkey_sig":
        #     "deposit": contract.deposit,
        #     # TODO: Whatever type "deposit" ends up being, we'll need to
        #     # serialize it here.  See #148.
        #     "expiration": contract.expiration,
        # }
        self.keystore.add_policy_contract(contract.expiration.datetime(),
                                          contract.deposit,
                                          hrac=contract.hrac.hex().encode(),
                                          alice_pubkey_sig=contract.alice.stamp
                                          )
        # TODO: Make the rest of this logic actually work - do something here
        # to decide if this Contract is worth accepting.
        return Response(
            b"This will eventually be an actual acceptance of the contract.",
            content_type="application/octet-stream")

    def set_policy(self, hrac_as_hex, request: http.Request):
        """
        REST endpoint for setting a kFrag.
        TODO: Instead of taking a Request, use the apistar typing system to type
            a payload and validate / split it.
        TODO: Validate that the kfrag being saved is pursuant to an approved
            Policy (see #121).
        """
        hrac = binascii.unhexlify(hrac_as_hex)
        policy_message_kit = MessageKit.from_bytes(request.body)
        # group_payload_splitter = BytestringSplitter(PublicKey)
        # policy_payload_splitter = BytestringSplitter((KFrag, KFRAG_LENGTH))

        alice = Alice.from_public_keys((SigningPower, policy_message_kit.alice_pubkey))
        self.learn_about_actor(alice)

        verified, cleartext = self.verify_from(
            alice, policy_message_kit,
            decrypt=True, signature_is_on_cleartext=True)

        if not verified:
            # TODO: What do we do if the Policy isn't signed properly?
            pass
        #
        # alices_signature, policy_payload =\
        #     BytestringSplitter(Signature)(cleartext, return_remainder=True)

        # TODO: If we're not adding anything else in the payload, stop using the
        # splitter here.
        # kfrag = policy_payload_splitter(policy_payload)[0]
        kfrag = KFrag.from_bytes(cleartext)

        # TODO: Query stored Contract and reconstitute
        policy_contract = self.keystore.get_policy_contract(hrac_as_hex.encode())
        # contract_details = self._contracts[hrac.hex()]

        if policy_contract.alice_pubkey_sig.key_data != alice.stamp:
            raise Alice.SuspiciousActivity

        # contract = Contract(alice=alice, hrac=hrac,
        #                     kfrag=kfrag, expiration=policy_contract.expiration)

        try:
            # TODO: Obviously we do this lower-level.
            policy_contract.k_frag = bytes(kfrag)
            self.keystore.session.commit()

        except IntegrityError:
            raise
            # Do something appropriately RESTful (ie, 4xx).

        return  # TODO: Return A 200, with whatever policy metadata.

    def reencrypt_via_rest(self, hrac_as_hex, request: http.Request):
        from nkms.policy.models import WorkOrder  # Avoid circular import
        hrac = binascii.unhexlify(hrac_as_hex)
        work_order = WorkOrder.from_rest_payload(hrac, request.body)
        kfrag_bytes = self.keystore.get_policy_contract(hrac.hex().encode()).k_frag  # Careful!  :-)
        # TODO: Push this to a lower level.
        kfrag = KFrag.from_bytes(kfrag_bytes)
        cfrag_byte_stream = b""

        for capsule in work_order.capsules:
            # TODO: Sign the result of this.  See #141.
            cfrag_byte_stream += bytes(pre.reencrypt(kfrag, capsule))

        # TODO: Put this in Ursula's datastore
        self._work_orders.append(work_order)

        return Response(content=cfrag_byte_stream,
                        content_type="application/octet-stream")

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
        return self.character._crypto_power.sign(*args, **kwargs)

    def __bytes__(self):
        return self.character._crypto_power.pubkey_sig_bytes()

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
        raise TypeError(
            "This isn't your SignatureStamp; it belongs to {} (a Stranger).  You can't sign with it.".format(self.character))


def congregate(*characters):
    for character in characters:
        for newcomer in characters:
            character.learn_about_actor(newcomer)
