import json
import random
import time
from collections import defaultdict
from decimal import Decimal
from typing import DefaultDict, Dict, List, Optional, Set, Tuple, Union

import maya
from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    SessionStaticKey,
    ThresholdDecryptionRequest,
    ThresholdDecryptionResponse,
)
from nucypher_core.ferveo import (
    AggregatedTranscript,
    CiphertextHeader,
    DecryptionSharePrecomputed,
    DecryptionShareSimple,
    DkgPublicKey,
    FerveoVariant,
    Transcript,
    Validator,
)
from web3 import HTTPProvider, Web3
from web3.exceptions import TransactionNotFound
from web3.types import TxReceipt

from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.models import PHASE1, PHASE2, Coordinator
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.trackers import dkg
from nucypher.blockchain.eth.trackers.bonding import OperatorBondedTracker
from nucypher.blockchain.eth.utils import truncate_checksum_address
from nucypher.crypto.powers import (
    CryptoPower,
    RitualisticPower,
    ThresholdRequestDecryptingPower,
    TransactingPower,
)
from nucypher.datastore.dkg import DKGStorage
from nucypher.policy.conditions.evm import _CONDITION_CHAINS
from nucypher.policy.conditions.utils import evaluate_condition_lingo
from nucypher.policy.payment import ContractPayment
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import Logger


class BaseActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    @validate_checksum_address
    def __init__(
        self,
        domain: TACoDomain,
        registry: ContractRegistry,
        transacting_power: Optional[TransactingPower] = None,
        checksum_address: Optional[ChecksumAddress] = None,
    ):
        if not (bool(checksum_address) ^ bool(transacting_power)):
            error = f'Pass transacting power or checksum address, got {checksum_address} and {transacting_power}.'
            raise ValueError(error)

        try:
            parent_address = self.checksum_address
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError(f"Can't have two different ethereum addresses. "
                                     f"Got {parent_address} and {checksum_address}.")
        except AttributeError:
            if transacting_power:
                self.checksum_address = transacting_power.account
            else:
                self.checksum_address = checksum_address

        self.transacting_power = transacting_power
        self.registry = registry
        self.domain = domain
        self._saved_receipts = list()  # track receipts of transmitted transactions

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_address)
        return r

    def __eq__(self, other) -> bool:
        """Actors are equal if they have the same address."""
        try:
            return bool(self.checksum_address == other.checksum_address)
        except AttributeError:
            return False

    @property
    def eth_balance(self) -> Decimal:
        """Return this actor's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
        balance = blockchain.client.get_balance(self.wallet_address)
        return Web3.from_wei(balance, 'ether')

    @property
    def wallet_address(self):
        return self.checksum_address


class NucypherTokenActor(BaseActor):
    """
    Actor to interface with the NuCypherToken contract
    """

    def __init__(self, registry: ContractRegistry, **kwargs):
        super().__init__(registry=registry, **kwargs)
        self.__token_agent = None


class Operator(BaseActor):
    READY_TIMEOUT = None  # (None or 0) == indefinite
    READY_POLL_RATE = 120  # seconds
    AGGREGATION_SUBMISSION_MAX_DELAY = 60
    LOG = Logger("operator")

    class OperatorError(BaseActor.ActorError):
        """Operator-specific errors."""

    class RitualNotFoundException(Exception):
        """Ritual is not found."""

    class UnauthorizedRequest(Exception):
        """Request is not authorized."""

    class DecryptionFailure(Exception):
        """Decryption failed."""

    def __init__(
        self,
        eth_endpoint: str,
        polygon_endpoint: str,
        pre_payment_method: ContractPayment,
        transacting_power: TransactingPower,
        signer: Signer = None,
        crypto_power: CryptoPower = None,
        client_password: str = None,
        operator_address: Optional[ChecksumAddress] = None,
        condition_blockchain_endpoints: Optional[Dict[int, List[str]]] = None,
        publish_finalization: bool = True,  # TODO: Remove this
        *args,
        **kwargs,
    ):
        # Falsy values may be passed down from the superclass
        if not eth_endpoint:
            raise ValueError("Ethereum endpoint URI is required to init an operator.")
        if not polygon_endpoint:
            raise ValueError("Polygon endpoint URI is required to init an operator.")
        if not pre_payment_method:
            raise ValueError("PRE payment method is required to init an operator.")

        if not transacting_power:
            transacting_power = TransactingPower(
                account=operator_address,
                password=client_password,
                signer=signer,
                cache=True,
            )

        # We pass the newly instantiated TransactingPower into consume_power_up here, even though it's accessible
        # on the instance itself (being composed in the __init__ of the base class, which we will call shortly)
        # because, given the need for initialization context, it's far less melodramatic
        # to do it here, and it's still available via the public crypto powers API.
        crypto_power.consume_power_up(transacting_power)

        self.pre_payment_method = pre_payment_method
        self._operator_bonded_tracker = OperatorBondedTracker(ursula=self)

        super().__init__(transacting_power=transacting_power, *args, **kwargs)
        self.log = Logger("operator")

        self.__staking_provider_address = None  # set by block_until_ready

        self.application_agent = ContractAgency.get_agent(
            TACoApplicationAgent,
            blockchain_endpoint=eth_endpoint,
            registry=self.registry,
        )

        registry = ContractRegistry.from_latest_publication(domain=self.domain)
        self.child_application_agent = ContractAgency.get_agent(
            TACoChildApplicationAgent,
            registry=registry,
            blockchain_endpoint=polygon_endpoint,
        )

        self.coordinator_agent = ContractAgency.get_agent(
            CoordinatorAgent,
            registry=registry,
            blockchain_endpoint=polygon_endpoint,
        )

        # track active onchain rituals
        self.ritual_tracker = dkg.ActiveRitualTracker(
            operator=self,
        )

        self.publish_finalization = (
            publish_finalization  # publish the DKG final key if True
        )
        # TODO: #3052 stores locally generated public DKG artifacts
        self.dkg_storage = DKGStorage()
        self.ritual_power = crypto_power.power_ups(
            RitualisticPower
        )  # ferveo material contained within
        self.threshold_request_power = crypto_power.power_ups(
            ThresholdRequestDecryptingPower
        )  # used for secure decryption request channel

        self.condition_providers = self.connect_condition_providers(
            condition_blockchain_endpoints
        )

    def set_provider_public_key(self) -> Union[TxReceipt, None]:
        # TODO: Here we're assuming there is one global key per node. See nucypher/#3167
        node_global_ferveo_key_set = self.coordinator_agent.is_provider_public_key_set(
            self.staking_provider_address
        )
        if not node_global_ferveo_key_set:
            receipt = self.coordinator_agent.set_provider_public_key(
                self.ritual_power.public_key(), transacting_power=self.transacting_power
            )
            return receipt

    @staticmethod
    def _is_permitted_condition_chain(chain_id: int) -> bool:
        return int(chain_id) in [int(cid) for cid in _CONDITION_CHAINS.keys()]

    @staticmethod
    def _make_condition_provider(uri: str) -> HTTPProvider:
        provider = HTTPProvider(endpoint_uri=uri)
        return provider

    def connect_condition_providers(
        self, endpoints: Dict[int, List[str]]
    ) -> DefaultDict[int, Set[HTTPProvider]]:
        providers = defaultdict(set)

        # check that we have endpoints for all condition chains
        if self.domain.condition_chain_ids != set(endpoints):
            raise self.ActorError(
                f"Missing blockchain endpoints for chains: "
                f"{self.domain.condition_chain_ids - set(endpoints)}"
            )

        # check that each chain id is supported
        for chain_id, endpoints in endpoints.items():
            if not self._is_permitted_condition_chain(chain_id):
                raise NotImplementedError(
                    f"Chain ID {chain_id} is not supported for condition evaluation by this Operator."
                )

            # connect to each endpoint and check that they are on the correct chain
            for uri in endpoints:
                provider = self._make_condition_provider(uri)
                if int(Web3(provider).eth.chain_id) != int(chain_id):
                    raise self.ActorError(
                        f"Condition blockchain endpoint {uri} is not on chain {chain_id}"
                    )
                providers[int(chain_id)].add(provider)

        humanized_chain_ids = ", ".join(
            _CONDITION_CHAINS[chain_id] for chain_id in providers
        )
        self.log.info(
            f"Connected to {len(providers)} blockchains for condition checking: {humanized_chain_ids}"
        )

        return providers

    def _resolve_validators(
        self,
        ritual: Coordinator.Ritual,
    ) -> List[Validator]:
        result = list()
        for staking_provider_address in ritual.providers:
            if self.checksum_address == staking_provider_address:
                # Local
                external_validator = Validator(
                    address=self.checksum_address,
                    public_key=self.ritual_power.public_key()
                )
            else:
                # Remote
                # TODO optimize rpc calls by obtaining public keys altogether
                #  instead of one-by-one?
                public_key = self.coordinator_agent.get_provider_public_key(
                    provider=staking_provider_address, ritual_id=ritual.id
                )
                self.log.debug(
                    f"Ferveo public key for {staking_provider_address} is {bytes(public_key).hex()[:-8:-1]}"
                )
                external_validator = Validator(
                    address=staking_provider_address, public_key=public_key
                )
            result.append(external_validator)
        result = sorted(result, key=lambda x: x.address)
        return result

    def publish_transcript(self, ritual_id: int, transcript: Transcript) -> HexBytes:
        tx_hash = self.coordinator_agent.post_transcript(
            ritual_id=ritual_id,
            transcript=transcript,
            transacting_power=self.transacting_power,
        )
        return tx_hash

    def publish_aggregated_transcript(
        self,
        ritual_id: int,
        aggregated_transcript: AggregatedTranscript,
        public_key: DkgPublicKey,
    ) -> HexBytes:
        """Publish an aggregated transcript to publicly available storage."""
        # look up the node index for this node on the blockchain
        participant_public_key = self.threshold_request_power.get_pubkey_from_ritual_id(
            ritual_id
        )
        tx_hash = self.coordinator_agent.post_aggregation(
            ritual_id=ritual_id,
            aggregated_transcript=aggregated_transcript,
            public_key=public_key,
            participant_public_key=participant_public_key,
            transacting_power=self.transacting_power,
        )
        return tx_hash

    def get_phase_receipt(
        self, ritual_id: int, phase: int
    ) -> Tuple[Optional[HexBytes], Optional[TxReceipt]]:
        if phase == 1:
            txhash = self.dkg_storage.get_transcript_txhash(ritual_id=ritual_id)
        elif phase == 2:
            txhash = self.dkg_storage.get_aggregation_txhash(ritual_id=ritual_id)
        else:
            raise ValueError(f"Invalid phase: '{phase}'.")
        if not txhash:
            return None, None
        try:
            blockchain = self.coordinator_agent.blockchain.client
            receipt = blockchain.get_transaction_receipt(txhash)
        except TransactionNotFound:
            return txhash, None

        # at least for now (pre dkg tracker) - clear since receipt obtained
        if phase == 1:
            self.dkg_storage.clear_transcript_txhash(ritual_id, txhash)
        else:
            self.dkg_storage.clear_aggregated_txhash(ritual_id, txhash)

        status = receipt.get("status")
        if status == 1:
            return txhash, receipt
        else:
            return None, None

    def _phase_has_pending_tx(self, ritual_id: int, phase: int) -> bool:
        tx_hash, _ = self.get_phase_receipt(ritual_id=ritual_id, phase=phase)
        if not tx_hash:
            return False
        self.log.info(
            f"Node {self.transacting_power.account} has pending tx {bytes(tx_hash).hex()} "
            f"for ritual #{ritual_id}, phase #{phase}; skipping execution"
        )
        return True

    def _is_phase_1_action_required(self, ritual_id: int) -> bool:
        """Check whether node needs to perform a DKG round 1 action."""
        # handle pending transactions
        if self._phase_has_pending_tx(ritual_id=ritual_id, phase=PHASE1):
            return False

        # check ritual status from the blockchain
        status = self.coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        if status != Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS:
            # This is a normal state when replaying/syncing historical
            # blocks that contain StartRitual events of pending or completed rituals.
            self.log.debug(
                f"ritual #{ritual_id} is not waiting for transcripts; status={status}; skipping execution"
            )
            return False

        # check the associated participant state
        participant = self.coordinator_agent.get_participant(
            ritual_id=ritual_id, provider=self.staking_provider_address, transcript=True
        )
        if participant.transcript:
            # This verifies that the node has not already submitted a transcript for this
            # ritual as read from the CoordinatorAgent.  This is a normal state, as
            # the node may have already submitted a transcript for this ritual.
            self.log.info(
                f"Node {self.transacting_power.account} has already posted a transcript for ritual "
                f"{ritual_id}; skipping execution"
            )
            return False

        return True

    def perform_round_1(
        self,
        ritual_id: int,
        authority: ChecksumAddress,
        participants: List[ChecksumAddress],
        timestamp: int,
    ) -> Optional[HexBytes]:
        """Perform round 1 of the DKG protocol for a given ritual ID on this node."""
        if self.checksum_address not in participants:
            # should never get here
            self.log.error(
                f"Not part of ritual {ritual_id}; no need to submit transcripts"
            )
            raise RuntimeError(
                f"Not participating in ritual {ritual_id}; should not have been notified"
            )

        # check phase 1 contract state
        if not self._is_phase_1_action_required(ritual_id=ritual_id):
            return

        ritual = self.coordinator_agent.get_ritual(
            ritual_id=ritual_id,
            transcripts=False,
        )

        self.log.debug(
            f"performing round 1 of DKG ritual "
            f"#{ritual_id} from blocktime {timestamp} "
            f"with authority {authority}."
        )

        # generate a transcript
        validators = self._resolve_validators(ritual)
        try:
            transcript = self.ritual_power.generate_transcript(
                nodes=validators,
                threshold=ritual.threshold,
                shares=ritual.shares,
                checksum_address=self.checksum_address,
                ritual_id=ritual.id,
            )
        except Exception as e:
            # TODO: Handle this better #3096
            self.log.critical(
                f"Failed to generate a transcript for ritual #{ritual.id}: {str(e)}"
            )
            raise e

        # store the transcript in the local cache
        self.dkg_storage.store_transcript(ritual_id=ritual.id, transcript=transcript)

        # publish the transcript and store the receipt
        tx_hash = self.publish_transcript(ritual_id=ritual.id, transcript=transcript)
        self.dkg_storage.store_transcript_txhash(ritual_id=ritual.id, txhash=tx_hash)

        # logging
        arrival = ritual.total_transcripts + 1
        self.log.debug(
            f"{self.transacting_power.account[:8]} submitted a transcript for "
            f"DKG ritual #{ritual.id} ({arrival}/{ritual.dkg_size}) with authority {authority}."
        )
        return tx_hash

    def _is_phase_2_action_required(self, ritual_id: int) -> bool:
        """Check whether node needs to perform a DKG round 2 action."""
        # check if there is a pending tx for this ritual + round combination
        if self._phase_has_pending_tx(ritual_id=ritual_id, phase=PHASE2):
            return False

        # check ritual status from the blockchain
        status = self.coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        if status != Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS:
            # This is a normal state when replaying/syncing historical
            # blocks that contain StartRitual events of pending or completed rituals.
            self.log.debug(
                f"ritual #{ritual_id} is not waiting for aggregations; status={status}."
            )
            return False

        # check the associated participant state
        participant = self.coordinator_agent.get_participant(
            ritual_id=ritual_id,
            provider=self.staking_provider_address,
            transcript=False,
        )
        if participant.aggregated:
            # This is a normal state, as the node may have already submitted an aggregated
            # transcript for this ritual, and it's not necessary to submit another one. Carry on.
            self.log.debug(
                f"Node {self.transacting_power.account} has already posted an "
                f"aggregated transcript for ritual {ritual_id}."
            )
            return False

        return True

    def perform_round_2(self, ritual_id: int, timestamp: int) -> Optional[HexBytes]:
        """Perform round 2 of the DKG protocol for the given ritual ID on this node."""
        # check phase 2 state
        if not self._is_phase_2_action_required(ritual_id=ritual_id):
            return

        ritual = self.coordinator_agent.get_ritual(
            ritual_id=ritual_id,
            transcripts=True,
        )

        # prepare the DKG artifacts and aggregate transcripts
        self.log.debug(
            f"{self.transacting_power.account[:8]} performing phase 2 "
            f"of DKG ritual #{ritual.id} from blocktime {timestamp}"
        )
        validators = self._resolve_validators(ritual)
        transcripts = (Transcript.from_bytes(bytes(t)) for t in ritual.transcripts)
        messages = list(zip(validators, transcripts))
        try:
            aggregated_transcript, dkg_public_key = (
                self.ritual_power.aggregate_transcripts(
                    threshold=ritual.threshold,
                    shares=ritual.shares,
                    checksum_address=self.checksum_address,
                    ritual_id=ritual.id,
                    transcripts=messages,
                )
            )
        except Exception as e:
            self.log.debug(
                f"Failed to aggregate transcripts for ritual #{ritual.id}: {str(e)}"
            )
            raise e

        # store the DKG artifacts for later optimized reads
        self.dkg_storage.store_aggregated_transcript(
            ritual_id=ritual.id, aggregated_transcript=aggregated_transcript
        )
        self.dkg_storage.store_public_key(
            ritual_id=ritual.id, public_key=dkg_public_key
        )

        # publish the transcript with network-wide jitter to avoid tx congestion
        time.sleep(random.randint(0, self.AGGREGATION_SUBMISSION_MAX_DELAY))
        tx_hash = self.publish_aggregated_transcript(
            ritual_id=ritual.id,
            aggregated_transcript=aggregated_transcript,
            public_key=dkg_public_key,
        )

        # store the receipt
        self.dkg_storage.store_aggregation_txhash(ritual_id=ritual.id, txhash=tx_hash)

        # logging
        total = ritual.total_aggregations + 1
        self.log.debug(
            f"{self.transacting_power.account[:8]} aggregated a transcript for "
            f"DKG ritual #{ritual.id} ({total}/{ritual.dkg_size})"
        )
        if total >= ritual.dkg_size:
            self.log.debug(f"DKG ritual #{ritual.id} should now be finalized")
        return tx_hash

    def derive_decryption_share(
        self,
        ritual_id: int,
        ciphertext_header: CiphertextHeader,
        aad: bytes,
        variant: FerveoVariant,
    ) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
        ritual = self.coordinator_agent.get_ritual(ritual_id)
        if not self.coordinator_agent.is_ritual_active(ritual_id=ritual.id):
            raise self.ActorError(f"Ritual #{ritual.id} is not active.")
        validators = list(self._resolve_validators(ritual))
        aggregated_transcript = AggregatedTranscript.from_bytes(bytes(ritual.aggregated_transcript))
        decryption_share = self.ritual_power.derive_decryption_share(
            nodes=validators,
            threshold=ritual.threshold,
            shares=ritual.shares,
            checksum_address=self.checksum_address,
            ritual_id=ritual.id,
            aggregated_transcript=aggregated_transcript,
            ciphertext_header=ciphertext_header,
            aad=aad,
            variant=variant
        )
        return decryption_share

    def decrypt_threshold_decryption_request(
        self, encrypted_request: EncryptedThresholdDecryptionRequest
    ) -> ThresholdDecryptionRequest:
        return self.threshold_request_power.decrypt_encrypted_request(
            encrypted_request=encrypted_request
        )

    def encrypt_threshold_decryption_response(
        self,
        decryption_response: ThresholdDecryptionResponse,
        requester_public_key: SessionStaticKey,
    ) -> EncryptedThresholdDecryptionResponse:
        return self.threshold_request_power.encrypt_decryption_response(
            decryption_response=decryption_response,
            requester_public_key=requester_public_key,
        )

    def _verify_active_ritual(self, decryption_request: ThresholdDecryptionRequest):
        # check that ritual is active
        if not self.coordinator_agent.is_ritual_active(
            ritual_id=decryption_request.ritual_id
        ):
            raise self.UnauthorizedRequest(
                f"Ritual #{decryption_request.ritual_id} is not active",
            )

        # enforces that the node is part of the ritual
        participating = self.coordinator_agent.is_participant(
            ritual_id=decryption_request.ritual_id, provider=self.checksum_address
        )
        if not participating:
            raise self.UnauthorizedRequest(
                f"Node not part of ritual {decryption_request.ritual_id}",
            )

    def _verify_ciphertext_authorization(
        self, decryption_request: ThresholdDecryptionRequest
    ) -> None:
        """check that the ciphertext is authorized for this ritual"""
        ciphertext_header = decryption_request.ciphertext_header
        authorization = decryption_request.acp.authorization
        if not self.coordinator_agent.is_encryption_authorized(
            ritual_id=decryption_request.ritual_id,
            evidence=authorization,
            ciphertext_header=bytes(ciphertext_header),
        ):
            raise self.UnauthorizedRequest(
                f"Encrypted data not authorized for ritual {decryption_request.ritual_id}",
            )

    def _evaluate_conditions(
        self, decryption_request: ThresholdDecryptionRequest
    ) -> None:
        # requester-supplied condition eval context
        context = None
        if decryption_request.context:
            # nucypher_core.Context -> str -> dict
            context = json.loads(str(decryption_request.context)) or dict()

        # obtain condition from request
        condition_lingo = json.loads(
            str(decryption_request.acp.conditions)
        )  # nucypher_core.Conditions -> str -> Lingo
        if not condition_lingo:
            # this should never happen for CBD - defeats the purpose
            raise self.UnauthorizedRequest(
                "No conditions present for ciphertext.",
            )

        # evaluate the conditions for this ciphertext; raises if it fails
        evaluate_condition_lingo(
            condition_lingo=condition_lingo,
            context=context,
            providers=self.condition_providers,
        )

    def _verify_decryption_request_authorization(
        self, decryption_request: ThresholdDecryptionRequest
    ) -> None:
        """check that the decryption request is authorized for this ritual"""
        self._verify_active_ritual(decryption_request)
        self._verify_ciphertext_authorization(decryption_request)
        self._evaluate_conditions(decryption_request)

    def _derive_decryption_share_for_request(
        self,
        decryption_request: ThresholdDecryptionRequest,
    ) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
        """Derive a decryption share for a given request"""
        self._verify_decryption_request_authorization(
            decryption_request=decryption_request
        )
        try:
            decryption_share = self.derive_decryption_share(
                ritual_id=decryption_request.ritual_id,
                ciphertext_header=decryption_request.ciphertext_header,
                aad=decryption_request.acp.aad(),
                variant=decryption_request.variant,
            )
        except Exception as e:
            self.log.warn(f"Failed to derive decryption share: {e}")
            raise self.DecryptionFailure(f"Failed to derive decryption share: {e}")
        return decryption_share

    def _encrypt_decryption_share(
        self,
        ritual_id: int,
        decryption_share: Union[DecryptionShareSimple, DecryptionSharePrecomputed],
        public_key: SessionStaticKey,
    ) -> EncryptedThresholdDecryptionResponse:
        # TODO: #3098 nucypher-core#49 Use DecryptionShare type
        decryption_response = ThresholdDecryptionResponse(
            ritual_id=ritual_id,
            decryption_share=bytes(decryption_share),
        )
        encrypted_response = self.encrypt_threshold_decryption_response(
            decryption_response=decryption_response,
            requester_public_key=public_key,
        )
        return encrypted_response

    def _local_operator_address(self):
        return self.__operator_address

    @property
    def wallet_address(self):
        return self.operator_address

    @property
    def staking_provider_address(self) -> ChecksumAddress:
        if not self.__staking_provider_address:
            self.__staking_provider_address = self.get_staking_provider_address()
        return self.__staking_provider_address

    def get_staking_provider_address(self) -> ChecksumAddress:
        self.__staking_provider_address = (
            self.child_application_agent.staking_provider_from_operator(
                self.operator_address
            )
        )
        self.checksum_address = self.__staking_provider_address
        self.nickname = Nickname.from_seed(self.checksum_address)
        return self.__staking_provider_address

    @property
    def is_confirmed(self) -> bool:
        return self.child_application_agent.is_operator_confirmed(self.operator_address)

    def block_until_ready(self, poll_rate: int = None, timeout: int = None):
        emitter = StdoutEmitter()
        poll_rate = poll_rate or self.READY_POLL_RATE
        timeout = timeout or self.READY_TIMEOUT
        start, funded, bonded = maya.now(), False, False

        taco_child_client = self.child_application_agent.blockchain.client
        taco_child_pretty_chain_name = PUBLIC_CHAINS.get(
            taco_child_client.chain_id, f"chain ID #{taco_child_client.chain_id}"
        )

        taco_root_chain_id = self.application_agent.blockchain.client.chain_id
        taco_root_pretty_chain_name = PUBLIC_CHAINS.get(
            taco_root_chain_id, f"chain ID #{taco_root_chain_id}"
        )
        while not (funded and bonded):
            if timeout and ((maya.now() - start).total_seconds() > timeout):
                message = f"x Operator was not qualified after {timeout} seconds"
                emitter.message(message, color="red")
                raise self.ActorError(message)

            if not funded:
                # check for funds
                matic_balance = taco_child_client.get_balance(self.operator_address)
                if matic_balance:
                    # funds found
                    funded, balance = True, Web3.from_wei(matic_balance, "ether")
                    emitter.message(
                        f"✓ Operator {self.operator_address} is funded with {balance} MATIC",
                        color="green",
                    )
                else:
                    emitter.message(
                        f"! Operator {self.operator_address} is not funded with MATIC",
                        color="yellow",
                    )

            if not bonded:
                # check root
                taco_root_bonded_address = (
                    self.application_agent.get_staking_provider_from_operator(
                        self.operator_address
                    )
                )
                if taco_root_bonded_address == NULL_ADDRESS:
                    emitter.message(
                        f"! Operator {self.operator_address} is not bonded to a staking provider",
                        color="yellow",
                    )
                else:
                    # check child
                    taco_child_bonded_address = self.get_staking_provider_address()
                    if taco_child_bonded_address == taco_root_bonded_address:
                        bonded = True
                        emitter.message(
                            f"✓ Operator {self.operator_address} is bonded to staking provider {self.staking_provider_address}",
                            color="green",
                        )
                    else:
                        child_bonded_address_info = (
                            f"({truncate_checksum_address(taco_child_bonded_address)})"
                            if taco_child_bonded_address != NULL_ADDRESS
                            else ""
                        )
                        emitter.message(
                            f"! Bonded staking provider address {truncate_checksum_address(taco_root_bonded_address)} on {taco_root_pretty_chain_name} not yet synced to child application on {taco_child_pretty_chain_name} {child_bonded_address_info}; waiting for sync",
                            color="yellow",
                        )

            if not (funded and bonded):
                time.sleep(poll_rate)

        coordinator_address = self.coordinator_agent.contract_address
        emitter.message(
            f"! Checking provider's DKG participation public key for {self.staking_provider_address} "
            f"on {taco_child_pretty_chain_name} at Coordinator {coordinator_address}",
            color="yellow",
        )
        receipt = self.set_provider_public_key()  # returns None if key already set
        if receipt:
            txhash = receipt["transactionHash"].hex()
            emitter.message(
                f"✓ Successfully published provider's DKG participation public key"
                f" for {self.staking_provider_address} on {taco_child_pretty_chain_name} with txhash {txhash})",
                color="green",
            )
        else:
            emitter.message(
                f"✓ Provider's DKG participation public key already set for "
                f"{self.staking_provider_address} on {taco_child_pretty_chain_name} at Coordinator {coordinator_address}",
                color="green",
            )

    def get_work_is_needed_check(self):
        def func(self):
            # we have not confirmed yet
            return not self.is_confirmed

        return func


class PolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, eth_endpoint: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.application_agent = ContractAgency.get_agent(
            TACoApplicationAgent,
            registry=self.registry,
            blockchain_endpoint=eth_endpoint,
        )

    def create_policy(self, *args, **kwargs):
        """Hence the name, a BlockchainPolicyAuthor can create a BlockchainPolicy with themself as the author."""
        from nucypher.policy.policies import Policy

        blockchain_policy = Policy(publisher=self, *args, **kwargs)
        return blockchain_policy
