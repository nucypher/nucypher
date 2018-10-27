import binascii
import random
from collections import OrderedDict
from functools import partial
from typing import Iterable, Callable
from typing import List

import maya
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_pem_x509_certificate, Certificate
from eth_utils import to_checksum_address
from twisted.internet import threads
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.blockchain.eth.actors import PolicyAuthor, Miner
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters.base import Character, Learner
from nucypher.config.storages import NodeStorage
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, PUBLIC_KEY_LENGTH
from nucypher.crypto.powers import SigningPower, EncryptingPower, DelegatingPower, BlockchainPower
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import VerifiableNode
from nucypher.network.protocols import InterfaceInfo
from nucypher.network.server import ProxyRESTServer, TLSHostingPower, ProxyRESTRoutes


class Alice(Character, PolicyAuthor):
    _default_crypto_powerups = [SigningPower, EncryptingPower, DelegatingPower]

    def __init__(self, is_me=True, federated_only=False, network_middleware=None, *args, **kwargs) -> None:

        policy_agent = kwargs.pop("policy_agent", None)
        checksum_address = kwargs.pop("checksum_address", None)
        Character.__init__(self,
                           is_me=is_me,
                           federated_only=federated_only,
                           checksum_address=checksum_address,
                           network_middleware=network_middleware,
                           *args, **kwargs)

        if is_me and not federated_only:  # TODO: 289
            PolicyAuthor.__init__(self, checksum_address=checksum_address)

    def generate_kfrags(self, bob, label: bytes, m: int, n: int) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.

        :param bob: Bob instance which will be able to decrypt messages re-encrypted with these kfrags.
        :param m: Minimum number of kfrags needed to activate a Capsule.
        :param n: Total number of kfrags to generate
        """

        bob_pubkey_enc = bob.public_keys(EncryptingPower)
        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        return delegating_power.generate_kfrags(bob_pubkey_enc, self.stamp, label, m, n)

    def create_policy(self, bob: "Bob", label: bytes, m: int, n: int, federated=False):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """
        public_key, kfrags = self.generate_kfrags(bob, label, m, n)

        payload = dict(label=label,
                       bob=bob,
                       kfrags=kfrags,
                       public_key=public_key,
                       m=m)

        if self.federated_only is True or federated is True:
            from nucypher.policy.models import FederatedPolicy
            # We can't sample; we can only use known nodes.
            known_nodes = self.shuffled_known_nodes()
            policy = FederatedPolicy(alice=self, ursulas=known_nodes, **payload)
        else:
            from nucypher.blockchain.eth.policies import BlockchainPolicy
            policy = BlockchainPolicy(author=self, **payload)

        return policy

    def grant(self, bob, uri, m=None, n=None, expiration=None, deposit=None, handpicked_ursulas=None):
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
                deposit = self.network_middleware.get_competitive_rate()
                if deposit == NotImplemented:
                    deposit = constants.NON_PAYMENT(b"0000000")
        if handpicked_ursulas is None:
            handpicked_ursulas = set()

        policy = self.create_policy(bob, uri, m, n)

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # deposit and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #
        # TODO: 289

        # If we're federated only, we need to block to make sure we have enough nodes.
        if self.federated_only and len(self.known_nodes) < n:
            good_to_go = self.block_until_number_of_known_nodes_is(n, learn_on_this_thread=True)
            if not good_to_go:
                raise ValueError(
                    "To make a Policy in federated mode, you need to know about\
                     all the Ursulas you need (in this case, {}); there's no other way to\
                      know which nodes to use.  Either pass them here or when you make\
                       the Policy, or run the learning loop on a network with enough Ursulas.".format(self.n))

            if len(handpicked_ursulas) < n:
                number_of_ursulas_needed = n - len(handpicked_ursulas)
                new_ursulas = random.sample(list(self.known_nodes.values()), number_of_ursulas_needed)
                handpicked_ursulas.update(new_ursulas)

        policy.make_arrangements(network_middleware=self.network_middleware,
                                 deposit=deposit,
                                 expiration=expiration,
                                 handpicked_ursulas=handpicked_ursulas,
                                 )

        # REST call happens here, as does population of TreasureMap.
        policy.enact(network_middleware=self.network_middleware)
        return policy  # Now with TreasureMap affixed!


class Bob(Character):
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from nucypher.policy.models import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
        self._saved_work_orders = WorkOrderHistory()

    def peek_at_treasure_map(self, treasure_map=None, map_id=None):
        """
        Take a quick gander at the TreasureMap matching map_id to see which
        nodes are already kwown to us.

        Don't do any learning, pinging, or anything other than just seeing
        whether we know or don't know the nodes.

        Return two sets: nodes that are unknown to us, nodes that are known to us.
        """
        if not treasure_map:
            if map_id:
                treasure_map = self.treasure_maps[map_id]
            else:
                raise ValueError("You need to pass either treasure_map or map_id.")
        else:
            if map_id:
                raise ValueError("Don't pass both treasure_map and map_id - pick one or the other.")

        # The intersection of the map and our known nodes will be the known Ursulas...
        known_treasure_ursulas = treasure_map.destinations.keys() & self.known_nodes.keys()

        # while the difference will be the unknown Ursulas.
        unknown_treasure_ursulas = treasure_map.destinations.keys() - self.known_nodes.keys()

        return unknown_treasure_ursulas, known_treasure_ursulas

    def follow_treasure_map(self,
                            treasure_map=None,
                            map_id=None,
                            block=False,
                            new_thread=False,
                            timeout=10,
                            allow_missing=0):
        """
        Follows a known TreasureMap, looking it up by map_id.

        Determines which Ursulas are known and which are unknown.

        If block, will block until either unknown nodes are discovered or until timeout seconds have elapsed.
        After timeout seconds, if more than allow_missing nodes are still unknown, raises NotEnoughUrsulas.

        If block and new_thread, does the same thing but on a different thread, returning a Deferred which
        fires after the blocking has concluded.

        Otherwise, returns (unknown_nodes, known_nodes).

        # TODO: Check if nodes are up, declare them phantom if not.
        """
        if not treasure_map:
            if map_id:
                treasure_map = self.treasure_maps[map_id]
            else:
                raise ValueError("You need to pass either treasure_map or map_id.")
        else:
            if map_id:
                raise ValueError("Don't pass both treasure_map and map_id - pick one or the other.")

        unknown_ursulas, known_ursulas = self.peek_at_treasure_map(treasure_map=treasure_map)

        if unknown_ursulas:
            self.learn_about_specific_nodes(unknown_ursulas)

        self._push_certain_newly_discovered_nodes_here(known_ursulas, unknown_ursulas)

        if block:
            if new_thread:
                return threads.deferToThread(self.block_until_specific_nodes_are_known, unknown_ursulas,
                                             timeout=timeout,
                                             allow_missing=allow_missing)
            else:
                self.block_until_specific_nodes_are_known(unknown_ursulas,
                                                          timeout=timeout,
                                                          allow_missing=allow_missing,
                                                          learn_on_this_thread=True)

        return unknown_ursulas, known_ursulas

    def get_treasure_map(self, alice_verifying_key, label):
        _hrac, map_id = self.construct_hrac_and_map_id(verifying_key=alice_verifying_key, label=label)

        if not self.known_nodes and not self._learning_task.running:
            # Quick sanity check - if we don't know of *any* Ursulas, and we have no
            # plans to learn about any more, than this function will surely fail.
            raise self.NotEnoughTeachers

        treasure_map = self.get_treasure_map_from_known_ursulas(self.network_middleware,
                                                                map_id)

        alice = Alice.from_public_keys({SigningPower: alice_verifying_key})
        compass = self.make_compass_for_alice(alice)
        try:
            treasure_map.orient(compass)
        except treasure_map.InvalidSignature:
            raise  # TODO: Maybe do something here?
        else:
            self.treasure_maps[map_id] = treasure_map

        return treasure_map

    def make_compass_for_alice(self, alice):
        return partial(self.verify_from, alice, decrypt=True)

    def construct_policy_hrac(self, verifying_key, label):
        return keccak_digest(bytes(verifying_key) + self.stamp + label)

    def construct_hrac_and_map_id(self, verifying_key, label):
        hrac = self.construct_policy_hrac(verifying_key, label)
        map_id = keccak_digest(bytes(verifying_key) + hrac).hex()
        return hrac, map_id

    def get_treasure_map_from_known_ursulas(self, networky_stuff, map_id):
        """
        Iterate through swarm, asking for the TreasureMap.
        Return the first one who has it.
        TODO: What if a node gives a bunk TreasureMap?
        """
        for node in self.known_nodes.values():
            response = networky_stuff.get_treasure_map_from_node(node, map_id)

            if response.status_code == 200 and response.content:
                from nucypher.policy.models import TreasureMap
                treasure_map = TreasureMap.from_bytes(response.content)
                break
            else:
                continue  # TODO: Actually, handle error case here.
        else:
            # TODO: Work out what to do in this scenario - if Bob can't get the TreasureMap, he needs to rest on the learning mutex or something.
            assert False

        return treasure_map

    def generate_work_orders(self, map_id, *capsules, num_ursulas=None):
        from nucypher.policy.models import WorkOrder  # Prevent circular import

        try:
            treasure_map_to_use = self.treasure_maps[map_id]
        except KeyError:
            raise KeyError(
                "Bob doesn't have the TreasureMap {}; can't generate work orders.".format(map_id))

        generated_work_orders = OrderedDict()

        if not treasure_map_to_use:
            raise ValueError(
                "Bob doesn't have a TreasureMap to match any of these capsules: {}".format(
                    capsules))

        for node_id, arrangement_id in treasure_map_to_use:
            ursula = self.known_nodes[node_id]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[node_id]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    arrangement_id, capsules_to_include, ursula, self)
                generated_work_orders[node_id] = work_order
                self._saved_work_orders[node_id][capsule] = work_order

            if num_ursulas is not None:
                if num_ursulas == len(generated_work_orders):
                    break

        return generated_work_orders

    def get_reencrypted_cfrags(self, work_order):
        cfrags = self.network_middleware.reencrypt(work_order)
        for counter, capsule in enumerate(work_order.capsules):
            # TODO: Maybe just update the work order here instead of setting it anew.
            work_orders_by_ursula = self._saved_work_orders[work_order.ursula.checksum_public_address]
            work_orders_by_ursula[capsule] = work_order
        return cfrags

    def get_ursula(self, ursula_id):
        return self._ursulas[ursula_id]

    def join_policy(self, label, alice_pubkey_sig, node_list=None):
        if node_list:
            self._node_ids_to_learn_about_immediately.update(node_list)
        treasure_map = self.get_treasure_map(alice_pubkey_sig, label)
        self.follow_treasure_map(treasure_map=treasure_map)

    def retrieve(self, message_kit, data_source, alice_verifying_key):

        message_kit.capsule.set_correctness_keys(
            delegating=data_source.policy_pubkey,
            receiving=self.public_keys(EncryptingPower),
            verifying=alice_verifying_key)

        hrac, map_id = self.construct_hrac_and_map_id(alice_verifying_key, data_source.label)
        self.follow_treasure_map(map_id=map_id, block=True)

        work_orders = self.generate_work_orders(map_id, message_kit.capsule)

        cleartexts = []

        for work_order in work_orders.values():
            cfrags = self.get_reencrypted_cfrags(work_order)
            message_kit.capsule.attach_cfrag(cfrags[0])

        delivered_cleartext = self.verify_from(data_source,
                                               message_kit,
                                               decrypt=True,
                                               delegator_signing_key=alice_verifying_key)

        cleartexts.append(delivered_cleartext)
        return cleartexts


class Ursula(Character, VerifiableNode, Miner):
    _internal_splitter = BytestringSplitter((int, 4, {'byteorder': 'big'}),
                                            Signature,
                                            VariableLengthBytestring,
                                            (UmbralPublicKey, PUBLIC_KEY_LENGTH),
                                            (UmbralPublicKey, PUBLIC_KEY_LENGTH),
                                            PUBLIC_ADDRESS_LENGTH,
                                            VariableLengthBytestring,  # Certificate
                                            InterfaceInfo)
    _alice_class = Alice

    # TODO: Maybe this wants to be a registry, so that, for example,
    # TLSHostingPower still can enjoy default status, but on a different class
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    class NotEnoughUrsulas(Learner.NotEnoughTeachers, MinerAgent.NotEnoughMiners):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class NotFound(Exception):
        pass

    # TODO: 289
    def __init__(self,

                 # Ursula
                 rest_host: str,
                 rest_port: int,
                 certificate: Certificate = None,
                 certificate_filepath: str = None,

                 db_name: str = None,
                 db_filepath: str = None,
                 is_me: bool = True,
                 interface_signature=None,
                 timestamp=None,

                 # Blockchain
                 checksum_address: str = None,

                 # Character
                 passphrase: str = None,
                 abort_on_learning_error: bool = False,
                 federated_only: bool = False,
                 start_learning_now: bool = None,
                 crypto_power=None,
                 tls_curve: EllipticCurve = None,
                 known_nodes: Iterable = None,

                 **character_kwargs
                 ) -> None:

        #
        # Character
        #
        self._work_orders = list()
        Character.__init__(self,
                           is_me=is_me,
                           checksum_address=checksum_address,
                           start_learning_now=start_learning_now,
                           federated_only=federated_only,
                           crypto_power=crypto_power,
                           abort_on_learning_error=abort_on_learning_error,
                           known_nodes=known_nodes,
                           **character_kwargs)

        #
        # Self-Ursula
        #
        if is_me is True:           # TODO: 340
            self._stored_treasure_maps = dict()

            #
            # Staking Ursula
            #
            if not federated_only:
                Miner.__init__(self, is_me=is_me, checksum_address=checksum_address)

                # Access staking node via node's transacting keys  TODO: Better handle ephemeral staking self ursula
                blockchain_power = BlockchainPower(blockchain=self.blockchain, account=self.checksum_public_address)
                self._crypto_power.consume_power_up(blockchain_power)

                # Use blockchain power to substantiate stamp, instead of signing key
                self.substantiate_stamp(passphrase=passphrase)  # TODO: Derive from keyring

        #
        # ProxyRESTServer and TLSHostingPower # TODO: Maybe we want _power_ups to be public after all?
        #
        if not crypto_power or (TLSHostingPower not in crypto_power._power_ups):

            #
            # Ephemeral Self-Ursula
            #
            if is_me:
                self.suspicious_activities_witnessed = {'vladimirs': [], 'bad_treasure_maps': []}

                #
                # REST Server (Ephemeral Self-Ursula)
                #
                rest_routes = ProxyRESTRoutes(
                    db_name=db_name,
                    db_filepath=db_filepath,
                    network_middleware=self.network_middleware,
                    federated_only=self.federated_only,   # TODO: 466
                    treasure_map_tracker=self.treasure_maps,
                    node_tracker=self.known_nodes,
                    node_bytes_caster=self.__bytes__,
                    work_order_tracker=self._work_orders,
                    node_recorder=self.remember_node,
                    stamp=self.stamp,
                    verifier=self.verify_from,
                    suspicious_activity_tracker=self.suspicious_activities_witnessed,
                    certificate_dir=self.known_certificates_dir,
                )

                #
                # TLSHostingPower (Ephemeral Self-Ursula)
                #
                tls_hosting_keypair = HostingKeypair(curve=tls_curve, host=rest_host)
                tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=rest_host)
                self.rest_server = ProxyRESTServer(rest_host=rest_host, rest_port=rest_port,
                                                   routes=rest_routes, hosting_power=tls_hosting_power)

            #
            # Stranger-Ursula
            #
            else:

                # TLSHostingPower
                if certificate or certificate_filepath:
                    tls_hosting_power = TLSHostingPower(host=rest_host,
                                                        public_certificate_filepath=certificate_filepath,
                                                        public_certificate=certificate)
                else:
                    tls_hosting_keypair = HostingKeypair(curve=tls_curve, host=rest_host)
                    tls_hosting_power = TLSHostingPower(host=rest_host, keypair=tls_hosting_keypair)

                # REST Server
                # Unless the caller passed a crypto power we'll make our own TLSHostingPower for this stranger.
                self.rest_server = ProxyRESTServer(
                    rest_host=rest_host,
                    rest_port=rest_port,
                    hosting_power=tls_hosting_power
                )

            #
            # OK - Now we have a ProxyRestServer and a TLSHostingPower for some Ursula
            #
            self._crypto_power.consume_power_up(tls_hosting_power)          # Consume!

        #
        # Verifiable Node
        #
        certificate_filepath = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate_filepath
        certificate = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate
        VerifiableNode.__init__(self,
                                certificate=certificate,
                                certificate_filepath=certificate_filepath,
                                interface_signature=interface_signature,
                                timestamp=timestamp)

        #
        # Logging
        #
        if is_me:
            message = "Initialized Self {} | {}".format(self.__class__.__name__, self.checksum_public_address)
            self.log.info(message)
        else:
            message = "Initialized Stranger {} | {}".format(self.__class__.__name__, self.checksum_public_address)
            self.log.debug(message)

    def rest_information(self):
        hosting_power = self._crypto_power.power_ups(TLSHostingPower)

        return (
            self.rest_server.rest_interface,
            hosting_power.keypair.certificate,
            hosting_power.keypair.pubkey
        )

    def get_deployer(self):
        port = self.rest_information()[0].port
        deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(rest_app=self.rest_app, port=port)
        return deployer

    def rest_server_certificate(self):  # TODO: relocate and use reference on TLS hosting power
        return self.get_deployer().cert.to_cryptography()

    def __bytes__(self):

        interface_info = VariableLengthBytestring(bytes(self.rest_information()[0]))
        identity_evidence = VariableLengthBytestring(self._evidence_of_decentralized_identity)

        certificate = self.rest_server_certificate()
        cert_vbytes = VariableLengthBytestring(certificate.public_bytes(Encoding.PEM))

        as_bytes = bytes().join((self.timestamp_bytes(),
                                 bytes(self._interface_signature),
                                 bytes(identity_evidence),
                                 bytes(self.public_keys(SigningPower)),
                                 bytes(self.public_keys(EncryptingPower)),
                                 self.canonical_public_address,
                                 bytes(cert_vbytes),
                                 bytes(interface_info))
                                )
        return as_bytes

    #
    # Alternate Constructors
    #

    @classmethod
    def from_rest_url(cls,
                      network_middleware: RestMiddleware,
                      host: str,
                      port: int,
                      certificate_filepath,
                      federated_only: bool = False) -> 'Ursula':

        response = network_middleware.node_information(host, port, certificate_filepath=certificate_filepath)
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))

        stranger_ursula_from_public_keys = cls.from_bytes(response.content, federated_only=federated_only)
        return stranger_ursula_from_public_keys

    @classmethod
    def from_bytes(cls,
                   ursula_as_bytes: bytes,
                   federated_only: bool = False,
                   ) -> 'Ursula':

        (timestamp,
         signature,
         identity_evidence,
         verifying_key,
         encrypting_key,
         public_address,
         certificate_vbytes,
         rest_info) = cls._internal_splitter(ursula_as_bytes)
        certificate = load_pem_x509_certificate(certificate_vbytes.message_as_bytes,
                                                default_backend())
        timestamp = maya.MayaDT(timestamp)
        stranger_ursula_from_public_keys = cls.from_public_keys(
            {SigningPower: verifying_key, EncryptingPower: encrypting_key},
            timestamp=timestamp,
            interface_signature=signature,
            checksum_address=to_checksum_address(public_address),
            rest_host=rest_info.host,
            rest_port=rest_info.port,
            certificate=certificate,
            federated_only=federated_only,  # TODO: 289
        )
        return stranger_ursula_from_public_keys

    @classmethod
    def batch_from_bytes(cls,
                         ursulas_as_bytes: Iterable[bytes],
                         federated_only: bool = False,
                         ) -> List['Ursula']:

        # TODO: Make a better splitter for this.  This is a workaround until bytestringSplitter #8 is closed.

        stranger_ursulas = []

        ursulas_attrs = cls._internal_splitter.repeat(ursulas_as_bytes)
        for (timestamp,
             signature,
             identity_evidence,
             verifying_key,
             encrypting_key,
             public_address,
             certificate_vbytes,
             rest_info) in ursulas_attrs:
            certificate = load_pem_x509_certificate(certificate_vbytes.message_as_bytes,
                                                    default_backend())
            timestamp = maya.MayaDT(timestamp)
            stranger_ursula_from_public_keys = cls.from_public_keys(
                {SigningPower: verifying_key,
                 EncryptingPower: encrypting_key,
                 },
                interface_signature=signature,
                timestamp=timestamp,
                checksum_address=to_checksum_address(public_address),
                certificate=certificate,
                rest_host=rest_info.host,
                rest_port=rest_info.port,
                federated_only=federated_only  # TODO: 289
            )
            stranger_ursulas.append(stranger_ursula_from_public_keys)

        return stranger_ursulas

    @classmethod
    def from_storage(cls,
                     node_storage: NodeStorage,
                     checksum_adress: str,
                     federated_only: bool = False) -> 'Ursula':
        return node_storage.get(checksum_address=checksum_adress,
                                federated_only=federated_only)

    #
    # Properties
    #
    @property
    def datastore(self):
        try:
            return self.rest_server.routes.datastore
        except AttributeError:
            raise AttributeError("No rest server attached")

    @property
    def rest_url(self):
        try:
            return self.rest_server.rest_url
        except AttributeError:
            raise AttributeError("No rest server attached")

    @property
    def rest_app(self):
        rest_app_on_server = self.rest_server.rest_app

        if not rest_app_on_server:
            m = "This Ursula doesn't have a REST app attached. If you want one, init with is_me and attach_server."
            raise AttributeError(m)
        else:
            return rest_app_on_server

    def interface_info_with_metadata(self):
        # TODO: Do we ever actually use this without using the rest of the serialized Ursula?  337
        return constants.BYTESTRING_IS_URSULA_IFACE_INFO + bytes(self)

    #
    # Utilities
    #

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
