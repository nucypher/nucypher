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
from web3.types import TxReceipt

from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    NucypherTokenAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.token import NU
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
        domain: str,
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
        self.network = domain
        self.taco_network = NetworksInventory.get_network(self.network)
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

    @property
    def token_agent(self):
        if self.__token_agent:
            return self.__token_agent
        self.__token_agent = ContractAgency.get_agent(
            NucypherTokenAgent,
            provider_uri=self.eth_provider_uri,
            registry=self.registry,
        )
        return self.__token_agent

    @property
    def token_balance(self) -> NU:
        """Return this actor's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance


class Operator(BaseActor):
    READY_TIMEOUT = None  # (None or 0) == indefinite
    READY_POLL_RATE = 10

    class OperatorError(BaseActor.ActorError):
        """Operator-specific errors."""

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
        condition_provider_uris: Optional[Dict[int, List[str]]] = None,
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
            provider_uri=eth_endpoint,
            registry=self.registry,
        )

        # TODO: registry usage (and subsequently "network") is inconsistent here
        registry = ContractRegistry.from_latest_publication(
            network=self.network
        )
        self.child_application_agent = ContractAgency.get_agent(
            TACoChildApplicationAgent,
            registry=registry,
            provider_uri=polygon_endpoint,
        )

        self.coordinator_agent = ContractAgency.get_agent(
            CoordinatorAgent,
            registry=registry,
            provider_uri=polygon_endpoint,
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
            condition_provider_uris
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
        self, condition_provider_uris: Optional[Dict[int, List[str]]] = None
    ) -> DefaultDict[int, Set[HTTPProvider]]:
        """Multi-provider support"""

        # If condition_provider_uris is None the node operator
        # did not configure any additional condition providers.
        condition_provider_uris = condition_provider_uris or dict()

        # These are the chains that the Operator will connect to for conditions evaluation (read-only).
        condition_providers = defaultdict(set)

        # Now, add any additional providers that were passed in.
        for chain_id, condition_provider_uris in condition_provider_uris.items():
            if not self._is_permitted_condition_chain(chain_id):
                # this is a safety check to prevent the Operator from connecting to
                # chains that are not supported by ursulas on the network;
                # Prevents the Ursula/Operator from starting up if this happens.
                raise NotImplementedError(
                    f"Chain ID {chain_id} is not supported for condition evaluation by this Operator."
                )

            providers = set()
            for uri in condition_provider_uris:
                provider = self._make_condition_provider(uri)
                providers.add(provider)

            condition_providers[int(chain_id)] = providers

        # Log the chains that the Operator is connected to.
        humanized_chain_ids = ", ".join(
            _CONDITION_CHAINS[chain_id] for chain_id in condition_providers
        )
        self.log.info(
            f"Connected to {len(condition_providers)} blockchains for condition checking: {humanized_chain_ids}"
        )

        return condition_providers

    def get_ritual(self, ritual_id: int) -> CoordinatorAgent.Ritual:
        try:
            ritual = self.ritual_tracker.rituals[ritual_id]
        except KeyError:
            raise self.ActorError(f"{ritual_id} is not in the local cache")
        return ritual

    def _resolve_validators(
            self,
            ritual: CoordinatorAgent.Ritual,
            timeout: int = 60
    ) -> List[Tuple[Validator, Transcript]]:

        validators = [n[0] for n in ritual.transcripts]
        if timeout > 0:
            nodes_to_discover = list(set(validators) - {self.checksum_address})
            self.block_until_specific_nodes_are_known(
                addresses=nodes_to_discover,
                timeout=timeout,
                allow_missing=0
            )

        result = list()
        for staking_provider_address, transcript_bytes in ritual.transcripts:
            if self.checksum_address == staking_provider_address:
                # Local
                external_validator = Validator(
                    address=self.checksum_address,
                    public_key=self.ritual_power.public_key()
                )
            else:
                # Remote
                try:
                    remote_operator = self.known_nodes[staking_provider_address]
                except KeyError:
                    raise self.ActorError(f"Unknown node {staking_provider_address}")
                remote_operator.mature()
                public_key = remote_operator.public_keys(RitualisticPower)
                self.log.debug(
                    f"Ferveo public key for {staking_provider_address} is {bytes(public_key).hex()[:-8:-1]}"
                )
                external_validator = Validator(
                    address=staking_provider_address, public_key=public_key
                )

            transcript = Transcript.from_bytes(transcript_bytes) if transcript_bytes else None
            result.append((external_validator, transcript))

        result = sorted(result, key=lambda x: x[0].address)
        return result

    def publish_transcript(self, ritual_id: int, transcript: Transcript) -> HexBytes:
        """Publish a transcript to publicly available storage."""
        # look up the node index for this node on the blockchain
        tx_hash = self.coordinator_agent.post_transcript(
            ritual_id=ritual_id,
            transcript=transcript,
            transacting_power=self.transacting_power,
            fire_and_forget=True,
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
            fire_and_forget=True,
        )
        return tx_hash

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
            raise self.RitualError(
                f"Not part of ritual {ritual_id}; don't post transcript"
            )

        # check ritual status from the blockchain
        status = self.coordinator_agent.get_ritual_status(ritual_id=ritual_id)

        # validate the status
        if status != CoordinatorAgent.Ritual.Status.AWAITING_TRANSCRIPTS:
            self.log.debug(
                f"ritual #{ritual_id} is not waiting for transcripts; status={status}; skipping execution"
            )
            return None

        # validate the active ritual tracker state
        participant = self.coordinator_agent.get_participant_from_provider(
            ritual_id=ritual_id, provider=self.checksum_address
        )
        if participant.transcript:
            self.log.debug(
                f"Node {self.transacting_power.account} has already posted a transcript for ritual {ritual_id}; skipping execution"
            )
            return None

        # check pending tx; since we check the coordinator contract
        # above, we know this tx is pending
        pending_tx = self.dkg_storage.get_transcript_receipt(ritual_id=ritual_id)
        if pending_tx:
            self.log.debug(
                f"Node {self.transacting_power.account} has pending tx {pending_tx} for posting transcript for ritual {ritual_id}; skipping execution"
            )
            return None

        self.log.debug(
            f"performing round 1 of DKG ritual #{ritual_id} from blocktime {timestamp} with authority {authority}."
        )

        # gather the cohort
        ritual = self.coordinator_agent.get_ritual(ritual_id, with_participants=True)
        nodes, transcripts = list(zip(*self._resolve_validators(ritual)))
        nodes = sorted(nodes, key=lambda n: n.address)
        if any(transcripts):
            self.log.debug(
                f"ritual #{ritual_id} is in progress {ritual.total_transcripts + 1}/{len(ritual.providers)}."
            )

        # generate a transcript
        try:
            transcript = self.ritual_power.generate_transcript(
                nodes=nodes,
                threshold=ritual.threshold,
                shares=ritual.shares,
                checksum_address=self.checksum_address,
                ritual_id=ritual_id
            )
        except Exception as e:
            # TODO: Handle this better #3096
            self.log.debug(f"Failed to generate a transcript for ritual #{ritual_id}: {str(e)}")
            raise e

        # store the transcript in the local cache
        self.dkg_storage.store_transcript(ritual_id=ritual_id, transcript=transcript)

        # publish the transcript and store the receipt
        tx_hash = self.publish_transcript(ritual_id=ritual_id, transcript=transcript)
        self.dkg_storage.store_transcript_receipt(
            ritual_id=ritual_id, txhash_or_receipt=tx_hash
        )

        arrival = ritual.total_transcripts + 1
        self.log.debug(
            f"{self.transacting_power.account[:8]} submitted a transcript for "
            f"DKG ritual #{ritual_id} ({arrival}/{len(ritual.providers)}) with authority {authority}."
        )
        return tx_hash

    def perform_round_2(self, ritual_id: int, timestamp: int) -> Optional[HexBytes]:
        """Perform round 2 of the DKG protocol for the given ritual ID on this node."""

        # Get the ritual and check the status from the blockchain
        # TODO potentially optimize local cache of ritual participants (#3052)
        status = self.coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        if status != CoordinatorAgent.Ritual.Status.AWAITING_AGGREGATIONS:
            self.log.debug(
                f"ritual #{ritual_id} is not waiting for aggregations; status={status}; skipping execution"
            )
            return None

        # validate the active ritual tracker state
        participant = self.coordinator_agent.get_participant_from_provider(
            ritual_id=ritual_id, provider=self.checksum_address
        )
        if participant.aggregated:
            self.log.debug(
                f"Node {self.transacting_power.account} has already posted an aggregated transcript for ritual {ritual_id}; skipping execution"
            )
            return None

        # check pending tx; since we check the coordinator contract
        # above, we know this tx is pending
        pending_tx = self.dkg_storage.get_aggregated_transcript_receipt(
            ritual_id=ritual_id
        )
        if pending_tx:
            self.log.debug(
                f"Node {self.transacting_power.account} has pending tx {pending_tx} for posting aggregated transcript for ritual {ritual_id}; skipping execution"
            )
            return None

        self.log.debug(
            f"{self.transacting_power.account[:8]} performing round 2 of DKG ritual #{ritual_id} from blocktime {timestamp}"
        )

        ritual = self.coordinator_agent.get_ritual(ritual_id, with_participants=True)
        transcripts = self._resolve_validators(ritual)
        if not all([t for _, t in transcripts]):
            raise self.ActorError(
                f"ritual #{ritual_id} is missing transcripts from {len([t for t in transcripts if not t])} nodes."
            )

        # Aggregate the transcripts
        try:
            result = self.ritual_power.aggregate_transcripts(
                threshold=ritual.threshold,
                shares=ritual.shares,
                checksum_address=self.checksum_address,
                ritual_id=ritual_id,
                transcripts=transcripts
            )
        except Exception as e:
            self.log.debug(f"Failed to aggregate transcripts for ritual #{ritual_id}: {str(e)}")
            raise e
        else:
            aggregated_transcript, dkg_public_key = result

        # Store the DKG artifacts for later us
        self.dkg_storage.store_aggregated_transcript(ritual_id=ritual_id, aggregated_transcript=aggregated_transcript)
        self.dkg_storage.store_public_key(ritual_id=ritual_id, public_key=dkg_public_key)

        # publish the transcript and store the receipt
        total = ritual.total_aggregations + 1
        tx_hash = self.publish_aggregated_transcript(
            ritual_id=ritual_id,
            aggregated_transcript=aggregated_transcript,
            public_key=dkg_public_key,
        )
        self.dkg_storage.store_aggregated_transcript_receipt(
            ritual_id=ritual_id, txhash_or_receipt=tx_hash
        )

        # logging
        self.log.debug(
            f"{self.transacting_power.account[:8]} aggregated a transcript for "
            f"DKG ritual #{ritual_id} ({total}/{len(ritual.providers)})"
        )
        if total >= len(ritual.providers):
            self.log.debug(f"DKG ritual #{ritual_id} should now be finalized")

        return tx_hash

    def derive_decryption_share(
        self,
        ritual_id: int,
        ciphertext_header: CiphertextHeader,
        aad: bytes,
        variant: FerveoVariant,
    ) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
        ritual = self.coordinator_agent.get_ritual(ritual_id)
        status = self.coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        if status != CoordinatorAgent.Ritual.Status.FINALIZED:
            raise self.ActorError(f"ritual #{ritual_id} is not finalized.")

        nodes, transcripts = list(zip(*self._resolve_validators(ritual)))
        if not all(transcripts):
            raise self.ActorError(
                f"ritual #{ritual_id} is missing transcripts"
            )

        # TODO: consider the usage of local DKG artifact storage here #3052
        # aggregated_transcript_bytes = self.dkg_storage.get_aggregated_transcript(ritual_id)
        aggregated_transcript = AggregatedTranscript.from_bytes(bytes(ritual.aggregated_transcript))
        decryption_share = self.ritual_power.derive_decryption_share(
            nodes=nodes,
            threshold=ritual.threshold,
            shares=ritual.shares,
            checksum_address=self.checksum_address,
            ritual_id=ritual_id,
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
            TACoApplicationAgent, registry=self.registry, provider_uri=eth_endpoint
        )

    def create_policy(self, *args, **kwargs):
        """Hence the name, a BlockchainPolicyAuthor can create a BlockchainPolicy with themself as the author."""
        from nucypher.policy.policies import Policy

        blockchain_policy = Policy(publisher=self, *args, **kwargs)
        return blockchain_policy
