import contextlib
import json
import time
from queue import Queue
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Union,
)

import maya
from constant_sorrow import constants
from constant_sorrow.constants import (
    INVALIDATED,
    NOT_SIGNED,
    PUBLIC_ONLY,
    READY,
    STRANGER_ALICE,
)
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from eth_typing.evm import ChecksumAddress
from eth_utils import to_checksum_address
from nucypher_core import (
    HRAC,
    AccessControlPolicy,
    Address,
    Conditions,
    Context,
    EncryptedKeyFrag,
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    EncryptedTreasureMap,
    MessageKit,
    NodeMetadata,
    NodeMetadataPayload,
    ReencryptionResponse,
    SessionStaticKey,
    SessionStaticSecret,
    ThresholdDecryptionRequest,
    ThresholdMessageKit,
    TreasureMap,
    encrypt_for_dkg,
)
from nucypher_core.ferveo import (
    DecryptionSharePrecomputed,
    DecryptionShareSimple,
    DkgPublicKey,
    FerveoVariant,
    Validator,
    combine_decryption_shares_precomputed,
    combine_decryption_shares_simple,
)
from nucypher_core.umbral import (
    PublicKey,
    RecoverableSignature,
    VerifiedKeyFrag,
    reencrypt,
)
from twisted.internet import reactor

import nucypher
from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import ArchivedFleetState, RemoteUrsulaStatus
from nucypher.blockchain.eth import actors
from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.banners import (
    ALICE_BANNER,
    BOB_BANNER,
    ENRICO_BANNER,
    URSULA_BANNER,
)
from nucypher.characters.base import Character, Learner
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.crypto.powers import (
    DecryptingPower,
    DelegatingPower,
    PowerUpError,
    RitualisticPower,
    SigningPower,
    ThresholdRequestDecryptingPower,
    TLSHostingPower,
    TransactingPower,
)
from nucypher.crypto.utils import keccak_digest
from nucypher.network.decryption import ThresholdDecryptionClient
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import NodeSprout, Teacher
from nucypher.network.protocols import parse_node_uri
from nucypher.network.retrieval import PRERetrievalClient
from nucypher.network.server import ProxyRESTServer, make_rest_app
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.policy.conditions.types import Lingo
from nucypher.policy.kits import PolicyMessageKit
from nucypher.policy.payment import ContractPayment, PaymentMethod
from nucypher.policy.policies import Policy
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import Logger
from nucypher.utilities.networking import validate_operator_ip
from nucypher.utilities.prometheus.metrics import (
    PrometheusMetricsConfig,
    start_prometheus_exporter,
)


class Alice(Character, actors.PolicyAuthor):
    banner = ALICE_BANNER
    _default_crypto_powerups = [SigningPower, DecryptingPower, DelegatingPower]

    def __init__(
        self,
        # Mode
        is_me: bool = True,
        eth_endpoint: str = None,
        signer=None,
        # Ownership
        checksum_address: Optional[ChecksumAddress] = None,
        # M of N
        threshold: Optional[int] = None,
        shares: Optional[int] = None,
        # Policy Value
        rate: int = None,
        duration: int = None,
        pre_payment_method: PaymentMethod = None,
        # Policy Storage
        store_policy_credentials: bool = None,
        # Middleware
        timeout: int = 10,  # seconds  # TODO: configure  NRN
        network_middleware: RestMiddleware = None,
        *args,
        **kwargs,
    ):
        #
        # Fallback Policy Values
        #

        self.timeout = timeout

        if is_me:
            self.threshold = threshold
            self.shares = shares

            self._policy_queue = Queue()
            self._policy_queue.put(READY)
        else:
            self.threshold = STRANGER_ALICE
            self.shares = STRANGER_ALICE

        Character.__init__(
            self,
            known_node_class=Ursula,
            is_me=is_me,
            eth_endpoint=eth_endpoint,
            checksum_address=checksum_address,
            network_middleware=network_middleware,
            *args,
            **kwargs,
        )

        if is_me:  # TODO: #289
            blockchain = BlockchainInterfaceFactory.get_interface(
                endpoint=self.eth_endpoint
            )
            signer = signer or Web3Signer(
                blockchain.client
            )  # fallback to web3 provider by default for Alice.
            self.transacting_power = TransactingPower(
                account=checksum_address, signer=signer
            )
            self._crypto_power.consume_power_up(self.transacting_power)
            actors.PolicyAuthor.__init__(
                self,
                domain=self.domain,
                transacting_power=self.transacting_power,
                registry=self.registry,
                eth_endpoint=eth_endpoint,
            )

        self.log = Logger(self.__class__.__name__)
        if is_me:
            # Policy Payment
            if not pre_payment_method:
                raise ValueError(
                    "pre_payment_method is a required argument for a local Alice."
                )
            self.pre_payment_method = pre_payment_method
            self.rate = rate
            self.duration = duration

            # Settings
            self.active_policies = dict()
            self.revocation_kits = dict()
            self.store_policy_credentials = store_policy_credentials

            self.log.info(self.banner)

    def add_active_policy(self, active_policy):
        """
        Adds a Policy object that is active on the TACo network to Alice's
        `active_policies` dictionary by the policy ID.
        """
        if active_policy.hrac in self.active_policies:
            raise KeyError("Policy already exists in active_policies.")
        self.active_policies[active_policy.hrac] = active_policy

    def generate_kfrags(
        self, bob: "Bob", label: bytes, threshold: int = None, shares: int = None
    ) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.

        :param bob: Bob instance which will be able to decrypt messages re-encrypted with these kfrags.
        :param m: Minimum number of kfrags needed to activate a Capsule.
        :param n: Total number of kfrags to generate
        """

        bob_encrypting_key = bob.public_keys(DecryptingPower)
        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        policy_key_and_kfrags = delegating_power.generate_kfrags(
            bob_pubkey_enc=bob_encrypting_key,
            signer=self.stamp.as_umbral_signer(),
            label=label,
            threshold=threshold or self.threshold,
            shares=shares or self.shares,
        )
        return policy_key_and_kfrags

    def create_policy(self, bob: "Bob", label: bytes, **policy_params):
        """
        Create a Policy so that Bob has access to all resources under label.
        Generates KFrags and attaches them.
        """

        policy_params = self.generate_policy_parameters(**policy_params)
        shares = policy_params.pop("shares")

        # Generate KFrags
        public_key, kfrags = self.generate_kfrags(
            bob=bob, label=label, threshold=policy_params["threshold"], shares=shares
        )
        payload = dict(
            label=label, bob=bob, kfrags=kfrags, public_key=public_key, **policy_params
        )

        # Sample from blockchain
        payload.update(**policy_params)
        policy = Policy(publisher=self, **payload)
        return policy

    def generate_policy_parameters(
        self,
        threshold: Optional[int] = None,
        shares: Optional[int] = None,
        duration: Optional[int] = None,
        commencement: Optional[maya.MayaDT] = None,
        expiration: Optional[maya.MayaDT] = None,
        value: Optional[int] = None,
        rate: Optional[int] = None,
        pre_payment_method: Optional[PaymentMethod] = None,
    ) -> dict:
        """Construct policy creation from default parameters or overrides."""

        if not duration and not expiration:
            raise ValueError(
                "Policy end time must be specified as 'expiration' or 'duration', got neither."
            )

        # Merge injected and default params.
        threshold = threshold or self.threshold
        shares = shares or self.shares
        duration = duration or self.duration
        rate = (
            rate if rate is not None else self.rate
        )  # TODO conflict with CLI default value, see #1709
        pre_payment_method = pre_payment_method or self.pre_payment_method

        # Calculate Policy Rate, Duration, and Value
        quote = self.pre_payment_method.quote(
            shares=shares,
            duration=duration,
            commencement=commencement.epoch if commencement else None,
            expiration=expiration.epoch if expiration else None,
            rate=rate,
            value=value,
        )

        params = dict(
            pre_payment_method=pre_payment_method,
            threshold=threshold,
            shares=shares,
            duration=quote.duration,
            commencement=quote.commencement,
            expiration=quote.expiration,
            rate=quote.rate,
            value=quote.value,
        )
        return params

    def _check_grant_requirements(self, policy):
        """Called immediately before granting."""
        # TODO: Do not allow policies with an expiration beyond a node unbonding time.

        # Policy Probationary Period
        # TODO: Remove when the time is right.
        # from nucypher.config.constants import END_OF_POLICIES_PROBATIONARY_PERIOD
        # if policy.expiration > END_OF_POLICIES_PROBATIONARY_PERIOD:
        #     raise RuntimeError(f"The requested duration for this policy (until {policy.expiration}) exceeds the "
        #                        f"probationary period ({END_OF_POLICIES_PROBATIONARY_PERIOD}).")

    def grant(
        self,
        bob: "Bob",
        label: bytes,
        ursulas: set = None,
        timeout: int = None,
        **policy_params,
    ):
        timeout = timeout or self.timeout

        #
        # Policy Creation
        #

        if ursulas:
            # This might be the first time alice learns about the handpicked Ursulas.
            for handpicked_ursula in ursulas:
                self.remember_node(node=handpicked_ursula)

        policy = self.create_policy(bob=bob, label=label, **policy_params)
        self._check_grant_requirements(policy=policy)
        self.log.debug(f"Generated new policy proposal {policy} ... ")

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # value and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #

        self.log.debug(f"Enacting {policy} ... ")
        enacted_policy = policy.enact(
            network_middleware=self.network_middleware, ursulas=ursulas
        )

        self.add_active_policy(enacted_policy)
        return enacted_policy

    def get_policy_encrypting_key_from_label(self, label: bytes) -> PublicKey:
        alice_delegating_power = self._crypto_power.power_ups(DelegatingPower)
        policy_pubkey = alice_delegating_power.get_pubkey_from_label(label)
        return policy_pubkey

    def decrypt_message_kit(self, label: bytes, message_kit: MessageKit) -> List[bytes]:
        """
        Decrypt this Alice's own encrypted data.

        I/O signatures match Bob's retrieve interface.
        """

        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        decrypting_power = delegating_power.get_decrypting_power_from_label(label)
        cleartext = decrypting_power.decrypt_message_kit(message_kit)

        # TODO: why does it return a list of cleartexts but takes a single message kit?
        # Shouldn't it be able to take a list of them too?
        return [cleartext]


class Bob(Character):
    banner = BOB_BANNER
    _default_dkg_variant = FerveoVariant.Simple
    _default_crypto_powerups = [SigningPower, DecryptingPower]
    _threshold_decryption_client_class = ThresholdDecryptionClient

    class IncorrectCFragsReceived(Exception):
        """
        Raised when Bob detects incorrect CFrags returned by some Ursulas
        """

        def __init__(self, evidence: List):
            self.evidence = evidence

    def __init__(
        self,
        is_me: bool = True,
        verify_node_bonding: bool = False,
        eth_endpoint: str = None,
        polygon_endpoint: str = None,
        *args,
        **kwargs,
    ) -> None:
        Character.__init__(
            self,
            is_me=is_me,
            known_node_class=Ursula,
            verify_node_bonding=verify_node_bonding,
            eth_endpoint=eth_endpoint,
            polygon_endpoint=polygon_endpoint,
            *args,
            **kwargs,
        )

        coordinator_agent = None
        if polygon_endpoint:
            coordinator_agent = ContractAgency.get_agent(
                CoordinatorAgent,
                blockchain_endpoint=polygon_endpoint,
                registry=ContractRegistry.from_latest_publication(
                    domain=self.domain,
                ),
            )
        self.coordinator_agent = coordinator_agent

        # Cache of decrypted treasure maps
        self._treasure_maps: Dict[int, TreasureMap] = {}

        self.log = Logger(self.__class__.__name__)
        if is_me:
            self.log.info(self.banner)

    def _decrypt_treasure_map(
        self,
        encrypted_treasure_map: EncryptedTreasureMap,
        publisher_verifying_key: PublicKey,
    ) -> TreasureMap:
        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        return decrypting_power.decrypt_treasure_map(
            encrypted_treasure_map, publisher_verifying_key=publisher_verifying_key
        )

    def retrieve(
        self,
        message_kits: Sequence[Union[MessageKit, PolicyMessageKit]],
        alice_verifying_key: PublicKey,  # KeyFrag signer's key
        encrypted_treasure_map: EncryptedTreasureMap,
        publisher_verifying_key: Optional[PublicKey] = None,
        timeout: int = PRERetrievalClient.DEFAULT_RETRIEVAL_TIMEOUT,
        **context,  # TODO: dont use one context to rule them all
    ) -> List[PolicyMessageKit]:
        """
        Attempts to retrieve reencrypted capsule fragments
        corresponding to given message kits from Ursulas.

        Accepts both "clean" message kits (obtained from a side channel)
        and "loaded" ones (with earlier retrieved capsule frags attached,
        along with the addresses of Ursulas they were obtained from).

        Returns a list of loaded message kits corresponding to the input list,
        with the kits containing the capsule fragments obtained during the retrieval.
        These kits can be used as an external cache to preserve the cfrags between
        several retrieval attempts.
        """

        if not publisher_verifying_key:
            publisher_verifying_key = alice_verifying_key
        publisher_verifying_key = PublicKey.from_compressed_bytes(
            publisher_verifying_key.to_compressed_bytes()
        )

        # A small optimization to avoid multiple treasure map decryptions.
        map_hash = hash(bytes(encrypted_treasure_map))
        if map_hash in self._treasure_maps:
            treasure_map = self._treasure_maps[map_hash]
        else:
            # Have to decrypt the treasure map first to find out what the threshold is.
            # Otherwise, we could check the message kits for completeness right away.
            treasure_map = self._decrypt_treasure_map(
                encrypted_treasure_map, publisher_verifying_key
            )
            self._treasure_maps[map_hash] = treasure_map

        # Normalize input
        message_kits: List[PolicyMessageKit] = [
            PolicyMessageKit.from_message_kit(
                message_kit, treasure_map.policy_encrypting_key, treasure_map.threshold
            )
            if isinstance(message_kit, MessageKit)
            else message_kit
            for message_kit in message_kits
        ]

        # Clear up all unrelated information from message kits before retrieval.
        retrieval_kits = [
            message_kit.as_retrieval_kit() for message_kit in message_kits
        ]

        # Retrieve capsule frags
        client = PRERetrievalClient(learner=self)
        retrieval_results, _ = client.retrieve_cfrags(
            treasure_map=treasure_map,
            retrieval_kits=retrieval_kits,
            alice_verifying_key=alice_verifying_key,
            bob_encrypting_key=self.public_keys(DecryptingPower),
            bob_verifying_key=self.stamp.as_umbral_pubkey(),
            context=context,
            timeout=timeout,
        )

        # Refill message kits with newly retrieved capsule frags
        results = []
        for message_kit, retrieval_result in zip(message_kits, retrieval_results):
            results.append(message_kit.with_result(retrieval_result))

        return results

    def retrieve_and_decrypt(self, *args, **kwds) -> List[bytes]:
        """
        Attempts to retrieve reencrypted capsule fragments from Ursulas
        and decrypt the ciphertexts in the given message kits.

        See ``retrieve()`` for the parameter list.
        """

        message_kits = self.retrieve(*args, **kwds)

        for message_kit in message_kits:
            if not message_kit.is_decryptable_by_receiver():
                raise Ursula.NotEnoughUrsulas(
                    f"Not enough cfrags retrieved to open capsule {message_kit.message_kit.capsule}"
                )

        cleartexts = []
        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        for message_kit in message_kits:
            cleartext = decrypting_power.decrypt_message_kit(message_kit)
            cleartexts.append(cleartext)

        return cleartexts

    @staticmethod
    def __make_decryption_request(
        ritual_id: int,
        threshold_message_kit: ThresholdMessageKit,
        variant: FerveoVariant,
        context: Optional[dict] = None,
    ) -> ThresholdDecryptionRequest:
        if context:
            context = Context(json.dumps(context))
        decryption_request = ThresholdDecryptionRequest(
            ritual_id=ritual_id,
            variant=variant,
            ciphertext_header=threshold_message_kit.ciphertext_header,
            acp=threshold_message_kit.acp,
            context=context,
        )
        return decryption_request

    def _get_decryption_shares(
        self,
        decryption_request: ThresholdDecryptionRequest,
        participant_public_keys: Dict[ChecksumAddress, SessionStaticKey],
        threshold: int,
        timeout: int,
    ) -> Dict[
        ChecksumAddress, Union[DecryptionShareSimple, DecryptionSharePrecomputed]
    ]:
        # use ephemeral key for request
        requester_sk = SessionStaticSecret.random()
        requester_public_key = requester_sk.public_key()

        decryption_request_mapping = {}
        shared_secrets = {}
        for (
            ursula_checksum_address,
            participant_public_key,
        ) in participant_public_keys.items():
            shared_secret = requester_sk.derive_shared_secret(participant_public_key)
            encrypted_decryption_request = decryption_request.encrypt(
                shared_secret=shared_secret,
                requester_public_key=requester_public_key,
            )
            shared_secrets[ursula_checksum_address] = shared_secret
            decryption_request_mapping[ursula_checksum_address] = (
                encrypted_decryption_request
            )

        decryption_client = self._threshold_decryption_client_class(learner=self)
        successes, failures = decryption_client.gather_encrypted_decryption_shares(
            encrypted_requests=decryption_request_mapping,
            threshold=threshold,
            timeout=timeout,
        )

        if len(successes) < threshold:
            raise Ursula.NotEnoughUrsulas(
                f"Threshold of Ursulas unable to decrypt: {failures}"
            )
        self.log.debug("Got enough shares to decrypt.")

        if decryption_request.variant == FerveoVariant.Precomputed:
            share_type = DecryptionSharePrecomputed
        elif decryption_request.variant == FerveoVariant.Simple:
            share_type = DecryptionShareSimple
        else:
            raise ValueError(
                f"Unknown decryption request variant: {decryption_request.variant}"
            )

        gathered_shares = {}
        for provider_address, encrypted_decryption_response in successes.items():
            shared_secret = shared_secrets[provider_address]
            decryption_response = encrypted_decryption_response.decrypt(
                shared_secret=shared_secret
            )
            decryption_share = share_type.from_bytes(
                decryption_response.decryption_share
            )
            gathered_shares[provider_address] = decryption_share
        return gathered_shares

    def _get_coordinator_agent(self) -> CoordinatorAgent:
        if not self.coordinator_agent:
            raise ValueError("No polygon endpoint URI provided in Bob's constructor.")

        return self.coordinator_agent

    def get_ritual_id_from_public_key(self, public_key: DkgPublicKey) -> int:
        ritual_id = self._get_coordinator_agent().get_ritual_id_from_public_key(
            public_key
        )
        return ritual_id

    def get_ritual(self, ritual_id) -> Coordinator.Ritual:
        agent = self._get_coordinator_agent()
        ritual = agent.get_ritual(ritual_id, transcripts=False)
        return ritual

    def threshold_decrypt(
        self,
        threshold_message_kit: ThresholdMessageKit,
        context: Optional[dict] = None,
        ursulas: Optional[List["Ursula"]] = None,
        decryption_timeout: int = ThresholdDecryptionClient.DEFAULT_DECRYPTION_TIMEOUT,
    ) -> bytes:
        ritual_id = self.get_ritual_id_from_public_key(
            public_key=threshold_message_kit.acp.public_key
        )
        ritual = self.get_ritual(ritual_id=ritual_id)

        if ursulas:
            for ursula in ursulas:
                if ursula.staking_provider_address not in ritual.providers:
                    raise ValueError(
                        f"{ursula} ({ursula.staking_provider_address}) is not part of the cohort"
                    )
                self.remember_node(ursula)

        variant = self._default_dkg_variant

        decryption_request = self.__make_decryption_request(
            ritual_id=ritual_id,
            threshold_message_kit=threshold_message_kit,
            variant=variant,
            context=context,
        )
        decryption_shares = self._get_decryption_shares(
            decryption_request=decryption_request,
            participant_public_keys=ritual.participant_public_keys,
            threshold=ritual.threshold,
            timeout=decryption_timeout,
        )

        return self.__decrypt(
            list(decryption_shares.values()),
            threshold_message_kit,
            variant,
        )

    @staticmethod
    def __decrypt(
        shares: List[Union[DecryptionShareSimple, DecryptionSharePrecomputed]],
        threshold_message_kit: ThresholdMessageKit,
        variant: FerveoVariant,
    ):
        """decrypt the ciphertext"""
        if variant == FerveoVariant.Precomputed:
            shared_secret = combine_decryption_shares_precomputed(shares)
        elif variant == FerveoVariant.Simple:
            shared_secret = combine_decryption_shares_simple(shares)
        else:
            raise ValueError(f"Invalid variant: {variant}.")

        cleartext = threshold_message_kit.decrypt_with_shared_secret(shared_secret)
        return cleartext


class Ursula(Teacher, Character, Operator):
    banner = URSULA_BANNER
    _alice_class = Alice

    _default_crypto_powerups = [
        SigningPower,
        DecryptingPower,
        RitualisticPower,
        ThresholdRequestDecryptingPower,
        # TLSHostingPower  # Still considered a default for Ursula, but needs the host context
    ]

    class NotEnoughUrsulas(Learner.NotEnoughTeachers):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class NotFound(Exception):
        pass

    def __init__(
        self,
        # Ursula
        rest_host: str,
        rest_port: int,
        domain: str,
        is_me: bool = True,
        certificate: Optional[Certificate] = None,
        metadata: Optional[NodeMetadata] = None,
        # Blockchain
        checksum_address: Optional[ChecksumAddress] = None,
        operator_address: Optional[ChecksumAddress] = None,
        client_password: Optional[str] = None,
        transacting_power: Optional[TransactingPower] = None,
        eth_endpoint: Optional[str] = None,
        polygon_endpoint: Optional[str] = None,
        condition_blockchain_endpoints: Optional[Dict[int, List[str]]] = None,
        pre_payment_method: Optional[Union[PaymentMethod, ContractPayment]] = None,
        # Character
        abort_on_learning_error: bool = False,
        crypto_power=None,
        known_nodes: Iterable[Teacher] = None,
        **character_kwargs,
    ):
        Character.__init__(
            self,
            is_me=is_me,
            checksum_address=checksum_address,
            crypto_power=crypto_power,
            abort_on_learning_error=abort_on_learning_error,
            known_nodes=known_nodes,
            domain=domain,
            known_node_class=Ursula,
            include_self_in_the_state=True,
            eth_endpoint=eth_endpoint,
            polygon_endpoint=polygon_endpoint,
            **character_kwargs,
        )

        if is_me:
            if metadata:
                raise ValueError("A local node must generate its own metadata.")
            self._metadata = None

            try:
                pre_payment_method: ContractPayment
                self.__operator_address = operator_address
                Operator.__init__(
                    self,
                    domain=self.domain,
                    registry=self.registry,
                    signer=self.signer,
                    crypto_power=self._crypto_power,
                    operator_address=operator_address,
                    eth_endpoint=eth_endpoint,
                    polygon_endpoint=polygon_endpoint,
                    pre_payment_method=pre_payment_method,
                    client_password=client_password,
                    condition_blockchain_endpoints=condition_blockchain_endpoints,
                    transacting_power=transacting_power,
                )

            except Exception:
                # It's not possible to finish constructing this node...
                # This block is here to ensure that the reactor is stopped in tests.
                self.stop(halt_reactor=False)
                raise

            # Use this power to substantiate the stamp
            self._substantiate_stamp()

            # Server
            self.rest_server = self._make_local_server(host=rest_host, port=rest_port)
            certificate = self._crypto_power.power_ups(
                TLSHostingPower
            ).keypair.certificate

            self.log.info(self.banner.format(self.nickname))

        else:
            # Peer HTTP Server
            # TODO: Use InterfaceInfo only
            self.rest_server = ProxyRESTServer(rest_host=rest_host, rest_port=rest_port)
            self._metadata = metadata
            self.__operator_address = None

        # Teacher (All Modes)
        Teacher.__init__(self, certificate=certificate)

        self._prometheus_metrics_tracker = None

    def _substantiate_stamp(self):
        transacting_power = self.transacting_power
        signature = transacting_power.sign_message(message=bytes(self.stamp))
        self.__operator_signature = signature
        self.__operator_address = transacting_power.account
        message = f"Created decentralized identity evidence: {self.__operator_signature[:10].hex()}"
        self.log.debug(message)

    @property
    def operator_signature(self):
        return self.__operator_signature

    @property
    def operator_address(self):
        # TODO (#2875): The reason for the fork here is the difference in available information
        # for local and remote nodes.
        # The local node knows its operator address, but doesn't yet know the staker address.
        # For the remote node, we know its staker address (from the metadata),
        # but don't know the worker address.
        # Can this be resolved more elegantly?
        if getattr(self, "is_me", False):
            return self._local_operator_address()
        else:
            if not self.__operator_address:
                address = self.metadata().payload.derive_operator_address()
                operator_address = to_checksum_address(bytes(address))
                self.__operator_address = operator_address
            return self.__operator_address

    def __get_hosting_power(self, host: str) -> TLSHostingPower:
        try:
            # Pre-existing or injected power
            tls_hosting_power = self._crypto_power.power_ups(TLSHostingPower)
        except TLSHostingPower.not_found_error:
            if self.keystore:
                # Derive TLS private key from seed
                tls_hosting_power = self.keystore.derive_crypto_power(
                    TLSHostingPower, host=host
                )
            else:
                # Generate ephemeral private key ("Dev Mode")
                tls_hosting_keypair = HostingKeypair(
                    host=host, generate_certificate=True
                )
                tls_hosting_power = TLSHostingPower(
                    keypair=tls_hosting_keypair, host=host
                )
            self._crypto_power.consume_power_up(tls_hosting_power)  # Consume!
        return tls_hosting_power

    def _make_local_server(self, host, port) -> ProxyRESTServer:
        rest_app = make_rest_app(this_node=self)
        rest_server = ProxyRESTServer(
            rest_host=host,
            rest_port=port,
            rest_app=rest_app,
            hosting_power=self.__get_hosting_power(host=host),
        )
        return rest_server

    def __preflight(self) -> None:
        """Called immediately before running services.
        If an exception is raised, Ursula startup will be interrupted."""
        validate_operator_ip(ip=self.rest_interface.host)

    def run(
        self,
        emitter: StdoutEmitter = None,
        discovery: bool = True,
        ritual_tracking: bool = True,
        hendrix: bool = True,
        start_reactor: bool = True,
        prometheus_config: PrometheusMetricsConfig = None,
        preflight: bool = True,
        block_until_ready: bool = True,
        eager: bool = False,
    ) -> None:
        """Schedule and start select ursula services, then optionally start the reactor."""

        BlockchainInterfaceFactory.get_or_create_interface(endpoint=self.eth_endpoint)
        BlockchainInterfaceFactory.get_or_create_interface(
            endpoint=self.polygon_endpoint
        )

        if preflight:
            self.__preflight()

        #
        # Async loops ordered by schedule priority
        #

        if emitter:
            emitter.message("Starting services...", color="yellow")

        if discovery and not self.lonely:
            self.start_learning_loop(now=eager)
            if emitter:
                emitter.message(f"✓ P2P Networking ({self.domain})", color="green")

        if ritual_tracking:
            self.ritual_tracker.start()
            if emitter:
                emitter.message("✓ DKG Ritual Tracking", color="green")

        if block_until_ready:
            # Sets (staker's) checksum address; Prevent worker startup before bonding
            self.block_until_ready()

        #
        # Non-order dependant services
        #

        # Continuous bonded check now that Ursula is all ready to run
        self._operator_bonded_tracker.start(now=eager)
        if emitter:
            emitter.message("✓ Start Operator Bonded Tracker", color="green")

        if prometheus_config:
            self._prometheus_metrics_tracker = start_prometheus_exporter(
                ursula=self, prometheus_config=prometheus_config
            )
            if emitter:
                prometheus_addr = (
                    prometheus_config.listen_address or self.rest_interface.host
                )
                emitter.message(
                    f"✓ Prometheus Exporter http://{prometheus_addr}:"
                    f"{prometheus_config.port}/metrics",
                    color="green",
                )

        if hendrix:
            if emitter:
                emitter.message(
                    f"✓ Rest Server https://{self.rest_interface}", color="green"
                )

            deployer = self.get_deployer()
            deployer.addServices()
            deployer.catalogServers(deployer.hendrix)

            if not start_reactor:
                return

            if emitter:
                emitter.message(
                    "Working ~ Keep Ursula Online!", color="blue", bold=True
                )

            try:
                deployer.run()  # <--- Blocking Call (Reactor)
            except Exception as e:
                self.log.critical(str(e))
                if emitter:
                    emitter.message(
                        f"{e.__class__.__name__} {e}", color="red", bold=True
                    )
                raise  # Crash :-(

        elif start_reactor:  # ... without hendrix
            reactor.run()  # <--- Blocking Call (Reactor)

    def stop(self, halt_reactor: bool = False) -> None:
        """
        Stop services for partially or fully initialized characters.
        # CAUTION #
        """
        self.log.debug(f"---------Stopping {self}")
        # Handles the shutdown of a partially initialized character.
        with contextlib.suppress(
            AttributeError
        ):  # TODO: Is this acceptable here, what are alternatives?
            self.stop_learning_loop()
            self._operator_bonded_tracker.stop()
            self.ritual_tracker.stop()
            if self._prometheus_metrics_tracker:
                self._prometheus_metrics_tracker.stop()
        if halt_reactor:
            reactor.stop()

    def _finalize(self):
        """
        Cleans up Ursula from objects that may eat up system resources.
        Useful for testing purposes, where many Ursulas are created and destroyed,
        and references to them may persist for too long.
        This method is not needed if all references to the Ursula are released.

        **Warning:** invalidates the Ursula.
        """
        self.rest_server = INVALIDATED

    def rest_information(self):
        hosting_power = self._crypto_power.power_ups(TLSHostingPower)

        return (
            self.rest_server.rest_interface,
            hosting_power.keypair.certificate,
            hosting_power.keypair.pubkey,
        )

    @property
    def rest_interface(self):
        return self.rest_server.rest_interface

    def get_deployer(self):
        port = self.rest_interface.port
        deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(
            rest_app=self.rest_app, port=port
        )
        return deployer

    @property
    def operator_signature_from_metadata(self):
        return self._metadata.payload.operator_signature or NOT_SIGNED

    def _generate_metadata(self) -> NodeMetadata:
        # Assuming that the attributes collected there do not change,
        # so we can cache the result of this method.
        # TODO: should this be a method of Teacher?
        timestamp = maya.now()

        # TODO: federated mode is gone, but for some reason a node may still not have
        # an operator signature created. Fill in a dummy value for now.
        operator_signature = self.operator_signature or (b"0" * 64 + b"\x00")

        operator_signature = RecoverableSignature.from_be_bytes(operator_signature)
        ferveo_public_key = self.public_keys(RitualisticPower)
        payload = NodeMetadataPayload(
            staking_provider_address=Address(self.canonical_address),
            domain=str(self.domain),
            timestamp_epoch=timestamp.epoch,
            verifying_key=self.public_keys(SigningPower),
            encrypting_key=self.public_keys(DecryptingPower),
            ferveo_public_key=ferveo_public_key,
            certificate_der=self.certificate.public_bytes(Encoding.DER),
            host=self.rest_interface.host,
            port=self.rest_interface.port,
            operator_signature=operator_signature,
        )
        return NodeMetadata(signer=self.stamp.as_umbral_signer(), payload=payload)

    def metadata(self):
        if not self._metadata:
            self._metadata = self._generate_metadata()
        return self._metadata

    @property
    def timestamp(self):
        return maya.MayaDT(self.metadata().payload.timestamp_epoch)

    #
    # Alternate Constructors
    #

    @classmethod
    def from_metadata_bytes(cls, metadata_bytes):
        # TODO: should be a method of `NodeSprout`, or maybe `NodeMetadata` *is* `NodeSprout`.
        # Fix when we get rid of inplace maturation.
        return NodeSprout(NodeMetadata.from_bytes(metadata_bytes))

    @classmethod
    def from_rest_url(cls, network_middleware: RestMiddleware, host: str, port: int):
        response_data = network_middleware.client.node_information(host, port)
        stranger_ursula_from_public_keys = cls.from_metadata_bytes(response_data)
        return stranger_ursula_from_public_keys

    @classmethod
    def from_seednode_metadata(cls, seednode_metadata, *args, **kwargs):
        """
        Essentially another deserialization method, but this one doesn't reconstruct a complete
        node from bytes; instead it's just enough to connect to and verify a node.
        """
        seed_uri = f"{seednode_metadata.checksum_address}@{seednode_metadata.rest_host}:{seednode_metadata.rest_port}"
        return cls.from_seed_and_stake_info(seed_uri=seed_uri, *args, **kwargs)

    @classmethod
    def from_teacher_uri(
        cls,
        teacher_uri: str,
        min_stake: int,
        eth_endpoint: str,
        registry: ContractRegistry = None,
        network_middleware: RestMiddleware = None,
        retry_attempts: int = 2,
        retry_interval: int = 2,
    ) -> "Ursula":
        def __attempt(attempt=1, interval=retry_interval) -> Ursula:
            if attempt >= retry_attempts:
                raise ConnectionRefusedError(
                    "Host {} Refused Connection".format(teacher_uri)
                )

            try:
                teacher = cls.from_seed_and_stake_info(
                    seed_uri=teacher_uri,
                    eth_endpoint=eth_endpoint,
                    minimum_stake=min_stake,
                    network_middleware=network_middleware,
                    registry=registry,
                )

            except NodeSeemsToBeDown:
                log = Logger(cls.__name__)
                log.warn(
                    "Can't connect to peer (attempt {}).  Will retry in {} seconds.".format(
                        attempt, interval
                    )
                )
                time.sleep(interval)
                return __attempt(attempt=attempt + 1)
            else:
                return teacher

        return __attempt()

    @classmethod
    def from_seed_and_stake_info(
        cls,
        seed_uri: str,
        eth_endpoint: str,
        registry: ContractRegistry = None,
        minimum_stake: int = 0,
        network_middleware: RestMiddleware = None,
    ) -> Union["Ursula", "NodeSprout"]:
        if network_middleware is None:
            network_middleware = RestMiddleware(
                registry=registry, eth_endpoint=eth_endpoint
            )

        # Parse node URI
        host, port, staking_provider_address = parse_node_uri(seed_uri)

        # Load the host as a potential seed node
        potential_seed_node = cls.from_rest_url(
            host=host,
            port=port,
            network_middleware=network_middleware,
        )

        # Check the node's stake (optional)
        if minimum_stake > 0 and staking_provider_address:
            application_agent = ContractAgency.get_agent(
                TACoApplicationAgent,
                blockchain_endpoint=eth_endpoint,
                registry=registry,
            )
            seednode_stake = application_agent.get_authorized_stake(
                staking_provider=staking_provider_address
            )
            if seednode_stake < minimum_stake:
                raise Learner.NotATeacher(
                    f"{staking_provider_address} is staking less than the specified minimum stake value ({minimum_stake})."
                )

        return potential_seed_node

    #
    # Properties
    #

    @property
    def rest_url(self):
        try:
            return self.rest_server.rest_url
        except AttributeError:
            raise AttributeError("No rest server attached")

    @property
    def rest_app(self):
        rest_app_on_server = self.rest_server.rest_app

        if rest_app_on_server is PUBLIC_ONLY or not rest_app_on_server:
            m = "This Ursula doesn't have a REST app attached. If you want one, init with is_me and attach_server."
            raise PowerUpError(m)
        else:
            return rest_app_on_server

    def interface_info_with_metadata(self):
        # TODO: Do we ever actually use this without using the rest of the serialized Ursula?  337
        return constants.BYTESTRING_IS_URSULA_IFACE_INFO + bytes(self)

    #
    # Re-Encryption
    #

    def _decrypt_kfrag(
        self,
        encrypted_kfrag: EncryptedKeyFrag,
        hrac: HRAC,
        publisher_verifying_key: PublicKey,
    ) -> VerifiedKeyFrag:
        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        return decrypting_power.decrypt_kfrag(
            encrypted_kfrag, hrac, publisher_verifying_key
        )

    def _reencrypt(self, kfrag: VerifiedKeyFrag, capsules) -> ReencryptionResponse:
        cfrags = []
        for capsule in capsules:
            cfrag = reencrypt(capsule, kfrag)
            cfrags.append(cfrag)
            self.log.info(f"Re-encrypted capsule {capsule} -> made {cfrag}.")
        results = list(zip(capsules, cfrags))
        return ReencryptionResponse(
            signer=self.stamp.as_umbral_signer(), capsules_and_vcfrags=results
        )

    def status_info(self, omit_known_nodes: bool = False) -> "LocalUrsulaStatus":
        domain = self.domain
        version = nucypher.__version__

        fleet_state = self.known_nodes.latest_state()
        previous_fleet_states = self.known_nodes.previous_states(4)

        if not omit_known_nodes:
            known_nodes_info = [
                self.known_nodes.status_info(node) for node in self.known_nodes
            ]
        else:
            known_nodes_info = None

        balance_eth = float(self.eth_balance)

        return LocalUrsulaStatus(
            nickname=self.nickname,
            staker_address=self.checksum_address,
            operator_address=self.operator_address,
            rest_url=self.rest_url(),
            timestamp=self.timestamp,
            domain=str(domain),
            version=version,
            fleet_state=fleet_state,
            previous_fleet_states=previous_fleet_states,
            known_nodes=known_nodes_info,
            balance_eth=balance_eth,
            block_height=self.ritual_tracker.scanner.get_last_scanned_block(),
        )

    def as_external_validator(self) -> Validator:
        """Returns an Validator instance for this Ursula for use in DKG operations."""
        validator = Validator(
            address=self.checksum_address, public_key=self.public_keys(RitualisticPower)
        )
        return validator

    def handle_threshold_decryption_request(
        self, encrypted_decryption_request: EncryptedThresholdDecryptionRequest
    ) -> EncryptedThresholdDecryptionResponse:
        decryption_request = self.decrypt_threshold_decryption_request(
            encrypted_decryption_request
        )
        decryption_share = self._derive_decryption_share_for_request(decryption_request)
        encrypted_response = self._encrypt_decryption_share(
            decryption_share=decryption_share,
            ritual_id=decryption_request.ritual_id,
            public_key=encrypted_decryption_request.requester_public_key,
        )
        return encrypted_response


class LocalUrsulaStatus(NamedTuple):
    nickname: Nickname
    staker_address: ChecksumAddress
    operator_address: str
    rest_url: str
    timestamp: maya.MayaDT
    domain: str
    version: str
    fleet_state: ArchivedFleetState
    previous_fleet_states: List[ArchivedFleetState]
    known_nodes: Optional[List[RemoteUrsulaStatus]]
    balance_eth: float
    block_height: int

    def to_json(self) -> Dict[str, Any]:
        if self.known_nodes is None:
            known_nodes_json = None
        else:
            known_nodes_json = [status.to_json() for status in self.known_nodes]
        return dict(
            nickname=self.nickname.to_json(),
            staker_address=self.staker_address,
            operator_address=self.operator_address,
            rest_url=self.rest_url,
            timestamp=self.timestamp.iso8601(),
            domain=self.domain,
            version=self.version,
            fleet_state=self.fleet_state.to_json(),
            previous_fleet_states=[
                state.to_json() for state in self.previous_fleet_states
            ],
            known_nodes=known_nodes_json,
            balance_eth=self.balance_eth,
            block_height=self.block_height,
        )


class Enrico:
    """A data source that encrypts data for some policy's public key"""

    banner = ENRICO_BANNER

    def __init__(
        self,
        encrypting_key: Union[PublicKey, DkgPublicKey],
        signer: Optional[Signer] = None,
    ):
        self.signer = signer
        self._encrypting_key = encrypting_key
        self.log = Logger(f"{self.__class__.__name__}-{encrypting_key}")
        self.log.info(self.banner.format(encrypting_key))

    def encrypt_for_pre(
        self, plaintext: bytes, conditions: Optional[Lingo] = None
    ) -> MessageKit:
        if conditions:
            condition_lingo = ConditionLingo.from_dict(conditions)
            conditions = Conditions(condition_lingo.to_json())
        message_kit = MessageKit(
            policy_encrypting_key=self.policy_pubkey,
            plaintext=plaintext,
            conditions=conditions,
        )
        return message_kit

    def encrypt_for_dkg(
        self,
        plaintext: bytes,
        conditions: Lingo,
    ) -> ThresholdMessageKit:
        if not self.signer:
            raise TypeError("This Enrico doesn't have a signer.")

        condition_lingo = ConditionLingo.from_dict(conditions)
        access_conditions = Conditions(condition_lingo.to_json())

        # encrypt for DKG
        ciphertext, auth_data = encrypt_for_dkg(
            plaintext, self.policy_pubkey, access_conditions
        )

        # authentication message for TACo
        header_hash = keccak_digest(bytes(ciphertext.header))
        authorization = bytes(
            self.signer.sign_message(
                message=header_hash, account=self.signer.accounts[0]
            )
        )

        return ThresholdMessageKit(
            ciphertext=ciphertext,
            acp=AccessControlPolicy(auth_data=auth_data, authorization=authorization),
        )

    @classmethod
    def from_alice(cls, alice: Alice, label: bytes):
        """
        :param alice: Not a stranger.  This is your Alice who will derive the policy keypair, leaving Enrico with the public part.
        :param label: The label with which to derive the key.
        :return:
        """
        policy_pubkey_enc = alice.get_policy_encrypting_key_from_label(label)
        return cls(encrypting_key=policy_pubkey_enc)

    @property
    def policy_pubkey(self):
        if not self._encrypting_key:
            raise TypeError(
                "This Enrico doesn't know which policy encrypting key he used.  Oh well."
            )
        return self._encrypting_key
