import os
import random
import sys
from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import accumulate
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
)

from constant_sorrow.constants import (
    # type: ignore
    CONTRACT_CALL,
    TRANSACTION,
)
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_checksum_address
from hexbytes import HexBytes
from nucypher_core import SessionStaticKey
from nucypher_core.ferveo import (
    AggregatedTranscript,
    DkgPublicKey,
    FerveoPublicKey,
    Transcript,
)
from web3.contract.contract import Contract, ContractFunction
from web3.types import Timestamp, TxParams, TxReceipt, Wei

from nucypher import types
from nucypher.blockchain.eth import events
from nucypher.blockchain.eth.constants import (
    ETH_ADDRESS_BYTE_LENGTH,
    NUCYPHER_TOKEN_CONTRACT_NAME,
    NULL_ADDRESS,
    SUBSCRIPTION_MANAGER_CONTRACT_NAME,
    TACO_APPLICATION_CONTRACT_NAME,
    TACO_CHILD_APPLICATION_CONTRACT_NAME,
)
from nucypher.blockchain.eth.decorators import contract_api
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
)
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE,
    NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE,
)
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import Logger


class EthereumContractAgent:
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    contract_name: str = NotImplemented
    _excluded_interfaces: Tuple[str, ...]

    # TODO - #842: Gas Management
    DEFAULT_TRANSACTION_GAS_LIMITS: Dict[str, Optional[Wei]]
    DEFAULT_TRANSACTION_GAS_LIMITS = {'default': None}

    class ContractNotDeployed(Exception):
        """Raised when attempting to access a contract that is not deployed on the current network."""

    class RequirementError(Exception):
        """
        Raised when an agent discovers a failed requirement in an invocation to a contract function,
        usually, a failed `require()`.
        """

    def __init__(
        self,
        blockchain_endpoint: str,
        registry: ContractRegistry,
        contract: Optional[Contract] = None,
        transaction_gas: Optional[Wei] = None,
    ):

        self.log = Logger(self.__class__.__name__)
        self.registry = registry

        self.blockchain = BlockchainInterfaceFactory.get_or_create_interface(
            blockchain_endpoint=blockchain_endpoint
        )

        if not contract:  # Fetch the contract
            contract = self.blockchain.get_contract_by_name(
                registry=registry,
                contract_name=self.contract_name,
            )

        self.__contract = contract
        self.events = events.ContractEvents(contract)
        if not transaction_gas:
            transaction_gas = EthereumContractAgent.DEFAULT_TRANSACTION_GAS_LIMITS['default']
        self.transaction_gas = transaction_gas

        self.log.info(
            "Initialized new {} for {} with {} and {}".format(
                self.__class__.__name__,
                self.contract.address,
                self.blockchain.blockchain_endpoint,
                str(self.registry),
            )
        )

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        r = "{}(registry={}, contract={})"
        return r.format(class_name, str(self.registry), self.contract_name)

    def __eq__(self, other: Any) -> bool:
        return bool(self.contract.address == other.contract.address)

    @property  # type: ignore
    def contract(self) -> Contract:
        return self.__contract

    @property  # type: ignore
    def contract_address(self) -> ChecksumAddress:
        return self.__contract.address


class NucypherTokenAgent(EthereumContractAgent):

    contract_name: str = NUCYPHER_TOKEN_CONTRACT_NAME

    @contract_api(CONTRACT_CALL)
    def get_balance(self, address: ChecksumAddress) -> types.NuNits:
        """Get the NU balance (in NuNits) of a token holder address, or of this contract address"""
        balance: int = self.contract.functions.balanceOf(address).call()
        return types.NuNits(balance)

    @contract_api(CONTRACT_CALL)
    def get_allowance(
        self, owner: ChecksumAddress, spender: ChecksumAddress
    ) -> types.NuNits:
        """Check the amount of tokens that an owner allowed to a spender"""
        allowance: int = self.contract.functions.allowance(owner, spender).call()
        return types.NuNits(allowance)

    @contract_api(TRANSACTION)
    def increase_allowance(
        self,
        transacting_power: TransactingPower,
        spender_address: ChecksumAddress,
        increase: types.NuNits,
    ) -> TxReceipt:
        """Increase the allowance of a spender address funded by a sender address"""
        contract_function: ContractFunction = self.contract.functions.increaseAllowance(spender_address, increase)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def decrease_allowance(
        self,
        transacting_power: TransactingPower,
        spender_address: ChecksumAddress,
        decrease: types.NuNits,
    ) -> TxReceipt:
        """Decrease the allowance of a spender address funded by a sender address"""
        contract_function: ContractFunction = self.contract.functions.decreaseAllowance(spender_address, decrease)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def approve_transfer(
        self,
        amount: types.NuNits,
        spender_address: ChecksumAddress,
        transacting_power: TransactingPower,
    ) -> TxReceipt:
        """Approve the spender address to transfer an amount of tokens on behalf of the sender address"""
        self._validate_zero_allowance(amount, spender_address, transacting_power)

        payload: TxParams = {'gas': Wei(500_000)}  # TODO #842: gas needed for use with geth! <<<< Is this still open?
        contract_function: ContractFunction = self.contract.functions.approve(spender_address, amount)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              payload=payload,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def transfer(
        self,
        amount: types.NuNits,
        target_address: ChecksumAddress,
        transacting_power: TransactingPower,
    ) -> TxReceipt:
        """Transfer an amount of tokens from the sender address to the target address."""
        contract_function: ContractFunction = self.contract.functions.transfer(target_address, amount)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def approve_and_call(
        self,
        amount: types.NuNits,
        target_address: ChecksumAddress,
        transacting_power: TransactingPower,
        call_data: bytes = b"",
        gas_limit: Optional[Wei] = None,
    ) -> TxReceipt:
        self._validate_zero_allowance(amount, target_address, transacting_power)

        payload = None
        if gas_limit:  # TODO: Gas management - #842
            payload = {'gas': gas_limit}
        approve_and_call: ContractFunction = self.contract.functions.approveAndCall(target_address, amount, call_data)
        approve_and_call_receipt: TxReceipt = self.blockchain.send_transaction(contract_function=approve_and_call,
                                                                               transacting_power=transacting_power,
                                                                               payload=payload)
        return approve_and_call_receipt

    def _validate_zero_allowance(self, amount, target_address, transacting_power):
        if amount == 0:
            return
        current_allowance = self.get_allowance(owner=transacting_power.account, spender=target_address)
        if current_allowance != 0:
            raise self.RequirementError(f"Token allowance for spender {target_address} must be 0")


class SubscriptionManagerAgent(EthereumContractAgent):

    contract_name: str = SUBSCRIPTION_MANAGER_CONTRACT_NAME

    class PolicyInfo(NamedTuple):
        sponsor: ChecksumAddress
        owner: ChecksumAddress
        start_timestamp: int
        end_timestamp: int

    #
    # Calls
    #

    @contract_api(CONTRACT_CALL)
    def fee_rate(self) -> Wei:
        result = self.contract.functions.feeRate().call()
        return Wei(result)

    @contract_api(CONTRACT_CALL)
    def is_policy_active(self, policy_id: bytes) -> bool:
        result = self.contract.functions.isPolicyActive(policy_id).call()
        return result

    @contract_api(CONTRACT_CALL)
    def fetch_policy(self, policy_id: bytes) -> PolicyInfo:
        record = self.contract.functions.policies(policy_id).call()
        policy_info = self.PolicyInfo(
            sponsor=record[0],
            start_timestamp=record[1],
            end_timestamp=record[2],
            size=record[3],
            # If the policyOwner addr is null, we return the sponsor addr instead of the owner.
            owner=record[0] if record[4] == NULL_ADDRESS else record[4]
        )
        return policy_info

    #
    # Transactions
    #

    @contract_api(TRANSACTION)
    def create_policy(self,
                      policy_id: bytes,
                      transacting_power: TransactingPower,
                      size: int,
                      start_timestamp: Timestamp,
                      end_timestamp: Timestamp,
                      value: Wei,
                      owner_address: Optional[ChecksumAddress] = None) -> TxReceipt:
        owner_address = owner_address or transacting_power.account
        payload: TxParams = {'value': value}
        contract_function: ContractFunction = self.contract.functions.createPolicy(
            policy_id,
            owner_address,
            size,
            start_timestamp,
            end_timestamp
        )
        receipt = self.blockchain.send_transaction(
            contract_function=contract_function,
            payload=payload,
            transacting_power=transacting_power
        )
        return receipt


class TACoChildApplicationAgent(EthereumContractAgent):
    contract_name: str = TACO_CHILD_APPLICATION_CONTRACT_NAME

    class StakingProviderInfo(NamedTuple):
        """Matching StakingProviderInfo struct from TACoChildApplication contract."""

        operator: ChecksumAddress
        operator_confirmed: bool
        authorized: int

    @contract_api(CONTRACT_CALL)
    def staking_provider_from_operator(
        self, operator_address: ChecksumAddress
    ) -> ChecksumAddress:
        result = self.contract.functions.stakingProviderFromOperator(
            operator_address
        ).call()
        return result

    @contract_api(CONTRACT_CALL)
    def staking_provider_info(
        self, staking_provider: ChecksumAddress
    ) -> StakingProviderInfo:
        result = self.contract.functions.stakingProviderInfo(staking_provider).call()
        return TACoChildApplicationAgent.StakingProviderInfo(*result)

    def is_operator_confirmed(self, operator_address: ChecksumAddress) -> bool:
        staking_provider = self.staking_provider_from_operator(operator_address)
        if staking_provider == NULL_ADDRESS:
            return False

        staking_provider_info = self.staking_provider_info(staking_provider)
        return staking_provider_info.operator_confirmed


class TACoApplicationAgent(EthereumContractAgent):
    contract_name: str = TACO_APPLICATION_CONTRACT_NAME

    DEFAULT_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE = int(os.environ.get(NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE, default=30))
    DEFAULT_PROVIDERS_PAGINATION_SIZE = int(os.environ.get(NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE, default=1000))

    class StakingProviderInfo(NamedTuple):
        operator: ChecksumAddress
        operator_confirmed: bool
        operator_start_timestamp: int

    class NotEnoughStakingProviders(Exception):
        pass

    class OperatorInfo(NamedTuple):
        address: ChecksumAddress
        confirmed: bool
        start_timestamp: Timestamp

    @contract_api(CONTRACT_CALL)
    def get_min_authorization(self) -> int:
        result = self.contract.functions.minimumAuthorization().call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_min_operator_seconds(self) -> int:
        result = self.contract.functions.minOperatorSeconds().call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_staking_provider_from_operator(self, operator_address: ChecksumAddress) -> ChecksumAddress:
        result = self.contract.functions.stakingProviderFromOperator(operator_address).call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_operator_from_staking_provider(self, staking_provider: ChecksumAddress) -> ChecksumAddress:
        result = self.contract.functions.getOperatorFromStakingProvider(staking_provider).call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_beneficiary(self, staking_provider: ChecksumAddress) -> ChecksumAddress:
        result = self.contract.functions.getBeneficiary(staking_provider).call()
        return result

    @contract_api(CONTRACT_CALL)
    def is_operator_confirmed(self, address: ChecksumAddress) -> bool:
        result = self.contract.functions.isOperatorConfirmed(address).call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_staking_provider_info(
        self, staking_provider: ChecksumAddress
    ) -> StakingProviderInfo:
        # remove reserved fields
        info: list = self.contract.functions.stakingProviderInfo(staking_provider).call()
        return TACoApplicationAgent.StakingProviderInfo(*info[0:3])

    @contract_api(CONTRACT_CALL)
    def get_authorized_stake(self, staking_provider: ChecksumAddress) -> int:
        result = self.contract.functions.authorizedStake(staking_provider).call()
        return result

    @contract_api(CONTRACT_CALL)
    def is_authorized(self, staking_provider: ChecksumAddress) -> bool:
        result = self.contract.functions.isAuthorized(staking_provider).call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_staking_providers_population(self) -> int:
        result = self.contract.functions.getStakingProvidersLength().call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_staking_providers(self) -> List[ChecksumAddress]:
        """Returns a list of staking provider addresses"""
        num_providers: int = self.get_staking_providers_population()
        providers: List[ChecksumAddress] = [self.contract.functions.stakingProviders(i).call() for i in range(num_providers)]
        return providers

    @contract_api(CONTRACT_CALL)
    def get_active_staking_providers(self, start_index: int, max_results: int) -> Iterable:
        result = self.contract.functions.getActiveStakingProviders(start_index, max_results).call()
        return result

    @contract_api(CONTRACT_CALL)
    def swarm(self) -> Iterable[ChecksumAddress]:
        for index in range(self.get_staking_providers_population()):
            address: ChecksumAddress = self.contract.functions.stakingProviders(index).call()
            yield address

    @contract_api(CONTRACT_CALL)
    def get_all_active_staking_providers(
        self, pagination_size: Optional[int] = None
    ) -> Tuple[types.TuNits, Dict[ChecksumAddress, types.TuNits]]:
        if pagination_size is None:
            pagination_size = self.DEFAULT_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE if self.blockchain.is_light else self.DEFAULT_PROVIDERS_PAGINATION_SIZE
            self.log.debug(f"Defaulting to pagination size {pagination_size}")
        elif pagination_size < 0:
            raise ValueError("Pagination size must be >= 0")

        if pagination_size > 0:
            num_providers: int = self.get_staking_providers_population()
            start_index: int = 0
            n_tokens: int = 0
            staking_providers: Dict[int, int] = dict()
            attempts: int = 0
            while start_index < num_providers:
                try:
                    attempts += 1
                    active_staking_providers = self.get_active_staking_providers(start_index, pagination_size)
                except Exception as e:
                    if 'timeout' not in str(e):
                        # exception unrelated to pagination size and timeout
                        raise e
                    elif pagination_size == 1 or attempts >= 3:
                        # we tried
                        raise e
                    else:
                        # reduce pagination size and retry
                        old_pagination_size = pagination_size
                        pagination_size = old_pagination_size // 2
                        self.log.debug(f"Failed staking providers sampling using pagination size = {old_pagination_size}."
                                       f"Retrying with size {pagination_size}")
                else:
                    temp_authorized_tokens, temp_staking_providers = active_staking_providers
                    # temp_staking_providers is a list of length-2 lists (address -> authorized tokens)
                    temp_staking_providers = {address: authorized_tokens for address, authorized_tokens in temp_staking_providers}
                    n_tokens = n_tokens + temp_authorized_tokens
                    staking_providers.update(temp_staking_providers)
                    start_index += pagination_size

        else:
            n_tokens, temp_staking_providers = self.get_active_staking_providers(start_index=0, max_results=0)
            staking_providers = {address: authorized_tokens for address, authorized_tokens in temp_staking_providers}

        # staking provider's addresses are returned as uint256 by getActiveStakingProviders(), convert to address objects
        def checksum_address(address: int) -> ChecksumAddress:
            return ChecksumAddress(to_checksum_address(address.to_bytes(ETH_ADDRESS_BYTE_LENGTH, 'big')))

        typed_staking_providers = {
            checksum_address(address): types.TuNits(authorized_tokens)
            for address, authorized_tokens in staking_providers.items()
        }

        return types.TuNits(n_tokens), typed_staking_providers

    def get_staking_provider_reservoir(self,
                                       without: Iterable[ChecksumAddress] = None,
                                       pagination_size: Optional[int] = None
                                       ) -> 'StakingProvidersReservoir':

        # pagination_size = pagination_size or self.get_staking_providers_population()
        n_tokens, stake_provider_map = self.get_all_active_staking_providers(pagination_size=pagination_size)

        filtered_out = 0
        if without:
            for address in without:
                if address in stake_provider_map:
                    n_tokens -= stake_provider_map[address]
                    del stake_provider_map[address]
                    filtered_out += 1

        self.log.debug(f"Got {len(stake_provider_map)} staking providers with {n_tokens} total tokens "
                       f"({filtered_out} filtered out)")
        if n_tokens == 0:
            raise self.NotEnoughStakingProviders("There are no locked tokens.")

        return StakingProvidersReservoir(stake_provider_map)

    #
    # Transactions
    #

    @contract_api(TRANSACTION)
    def bond_operator(self, staking_provider: ChecksumAddress, operator: ChecksumAddress, transacting_power: TransactingPower) -> TxReceipt:
        """For use by threshold operator accounts only."""
        contract_function: ContractFunction = self.contract.functions.bondOperator(staking_provider, operator)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   transacting_power=transacting_power)
        return receipt


class CoordinatorAgent(EthereumContractAgent):
    contract_name: str = "Coordinator"

    class G2Point(NamedTuple):
        """
        Coordinator contract representation of Ferveo Participant public key.
        """

        # TODO validation of these if used directly
        word0: bytes  # 32 bytes
        word1: bytes  # 32 bytes
        word2: bytes  # 32 bytes

        @classmethod
        def from_public_key(cls, public_key: FerveoPublicKey):
            return cls.from_bytes(bytes(public_key))

        @classmethod
        def from_bytes(cls, data: bytes):
            if len(data) != FerveoPublicKey.serialized_size():
                raise ValueError(
                    f"Invalid byte length; expected {FerveoPublicKey.serialized_size()} bytes but got {len(data)} bytes for G2Point"
                )
            return cls(word0=data[:32], word1=data[32:64], word2=data[64:96])

        def to_public_key(self) -> FerveoPublicKey:
            data = bytes(self)
            if not data:
                return None

            return FerveoPublicKey.from_bytes(data)

        def __bytes__(self):
            return self.word0 + self.word1 + self.word2

    @dataclass
    class Ritual:

        @dataclass
        class Status:
            NON_INITIATED = 0
            AWAITING_TRANSCRIPTS = 1
            AWAITING_AGGREGATIONS = 2
            TIMEOUT = 3
            INVALID = 4
            FINALIZED = 5

        @dataclass
        class Participant:
            provider: ChecksumAddress
            aggregated: bool = False
            transcript: bytes = bytes()
            decryption_request_static_key: bytes = bytes()

        class G1Point(NamedTuple):
            """Coordinator contract representation of DkgPublicKey."""

            # TODO validation of these if used directly
            word0: bytes  # 32 bytes
            word1: bytes  # 16 bytes

            @classmethod
            def from_dkg_public_key(cls, public_key: DkgPublicKey):
                return cls.from_bytes(bytes(public_key))

            @classmethod
            def from_bytes(cls, data: bytes):
                if len(data) != DkgPublicKey.serialized_size():
                    raise ValueError(
                        f"Invalid byte length; expected {DkgPublicKey.serialized_size()} bytes but got {len(data)} bytes for G1Point"
                    )
                return cls(word0=data[:32], word1=data[32:48])

            def to_dkg_public_key(self) -> DkgPublicKey:
                data = bytes(self)
                if not data:
                    return None

                return DkgPublicKey.from_bytes(data)

            def __bytes__(self):
                return self.word0 + self.word1

        initiator: ChecksumAddress
        authority: ChecksumAddress
        access_controller: ChecksumAddress
        dkg_size: int
        init_timestamp: int
        end_timestamp: int
        threshold: int

        total_transcripts: int = 0
        total_aggregations: int = 0
        public_key: G1Point = None
        aggregation_mismatch: bool = False
        aggregated_transcript: bytes = bytes()
        participants: List = field(default_factory=list)

        @property
        def providers(self):
            return [p.provider for p in self.participants]

        @property
        def transcripts(self) -> List[Tuple[ChecksumAddress, bytes]]:
            transcripts = list()
            for p in self.participants:
                transcripts.append((p.provider, p.transcript))
            return transcripts

        @property
        def shares(self) -> int:
            return len(self.providers)

        @property
        def participant_public_keys(self) -> Dict[ChecksumAddress, SessionStaticKey]:
            participant_public_keys = {}
            for p in self.participants:
                participant_public_keys[p.provider] = SessionStaticKey.from_bytes(
                    p.decryption_request_static_key
                )

            return participant_public_keys

    @contract_api(CONTRACT_CALL)
    def get_timeout(self) -> int:
        return self.contract.functions.timeout().call()

    @contract_api(CONTRACT_CALL)
    def get_ritual(self, ritual_id: int, with_participants: bool = True) -> Ritual:
        result = self.contract.functions.rituals(int(ritual_id)).call()
        ritual = self.Ritual(
            initiator=ChecksumAddress(result[0]),
            init_timestamp=result[1],
            end_timestamp=result[2],
            total_transcripts=result[3],
            total_aggregations=result[4],
            authority=ChecksumAddress(result[5]),
            dkg_size=result[6],
            threshold=result[7],
            aggregation_mismatch=result[8],
            access_controller=ChecksumAddress(result[9]),
            aggregated_transcript=bytes(result[11]),
            participants=[],  # solidity does not return sub-structs
        )

        # public key
        ritual.public_key = self.Ritual.G1Point(result[10][0], result[10][1])

        # participants
        if with_participants:
            participants = self.get_participants(ritual_id)
            ritual.participants = participants
        return ritual

    @contract_api(CONTRACT_CALL)
    def get_ritual_status(self, ritual_id: int) -> int:
        result = self.contract.functions.getRitualState(ritual_id).call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_participants(self, ritual_id: int) -> List[Ritual.Participant]:
        result = self.contract.functions.getParticipants(ritual_id).call()
        participants = list()
        for r in result:
            participant = self.Ritual.Participant(
                provider=ChecksumAddress(r[0]),
                aggregated=r[1],
                transcript=bytes(r[2]),
                decryption_request_static_key=bytes(r[3]),
            )
            participants.append(participant)
        return participants

    @contract_api(CONTRACT_CALL)
    def get_provider_public_key(
        self, provider: ChecksumAddress, ritual_id: int
    ) -> FerveoPublicKey:
        result = self.contract.functions.getProviderPublicKey(
            provider, ritual_id
        ).call()
        g2_point = self.G2Point(result[0], result[1], result[2])
        return g2_point.to_public_key()

    @contract_api(CONTRACT_CALL)
    def number_of_rituals(self) -> int:
        result = self.contract.functions.numberOfRituals().call()
        return result

    @contract_api(CONTRACT_CALL)
    def get_participant_from_provider(
        self, ritual_id: int, provider: ChecksumAddress
    ) -> Ritual.Participant:
        result = self.contract.functions.getParticipantFromProvider(
            ritual_id, provider
        ).call()
        participant = self.Ritual.Participant(
            provider=ChecksumAddress(result[0]),
            aggregated=result[1],
            transcript=bytes(result[2]),
            decryption_request_static_key=bytes(result[3]),
        )
        return participant

    @contract_api(CONTRACT_CALL)
    def is_encryption_authorized(
        self, ritual_id: int, evidence: bytes, ciphertext_header: bytes
    ) -> bool:
        """
        This contract read is relayed through coordinator to the access controller
        contract associated with a given ritual.
        """
        result = self.contract.functions.isEncryptionAuthorized(
            ritual_id, evidence, ciphertext_header
        ).call()
        return result

    @contract_api(CONTRACT_CALL)
    def is_provider_public_key_set(self, staking_provider: ChecksumAddress) -> bool:
        result = self.contract.functions.isProviderPublicKeySet(staking_provider).call()
        return result

    @contract_api(TRANSACTION)
    def set_provider_public_key(
        self, public_key: FerveoPublicKey, transacting_power: TransactingPower
    ) -> TxReceipt:
        contract_function = self.contract.functions.setProviderPublicKey(
            self.G2Point.from_public_key(public_key)
        )
        receipt = self.blockchain.send_transaction(
            contract_function=contract_function, transacting_power=transacting_power
        )
        return receipt

    @contract_api(TRANSACTION)
    def initiate_ritual(
        self,
        providers: List[ChecksumAddress],
        authority: ChecksumAddress,
        duration: int,
        access_controller: ChecksumAddress,
        transacting_power: TransactingPower,
    ) -> TxReceipt:
        contract_function: ContractFunction = self.contract.functions.initiateRitual(
            providers, authority, duration, access_controller
        )
        receipt = self.blockchain.send_transaction(
            contract_function=contract_function, transacting_power=transacting_power
        )
        return receipt

    @contract_api(TRANSACTION)
    def post_transcript(
        self,
        ritual_id: int,
        transcript: Transcript,
        transacting_power: TransactingPower,
        fire_and_forget: bool = False,
    ) -> Union[TxReceipt, HexBytes]:
        contract_function: ContractFunction = self.contract.functions.postTranscript(
            ritualId=ritual_id, transcript=bytes(transcript)
        )
        receipt = self.blockchain.send_transaction(
            contract_function=contract_function,
            transacting_power=transacting_power,
            fire_and_forget=fire_and_forget,
        )
        return receipt

    @contract_api(TRANSACTION)
    def post_aggregation(
        self,
        ritual_id: int,
        aggregated_transcript: AggregatedTranscript,
        public_key: DkgPublicKey,
        participant_public_key: SessionStaticKey,
        transacting_power: TransactingPower,
        fire_and_forget: bool = False,
    ) -> Union[TxReceipt, HexBytes]:
        contract_function: ContractFunction = self.contract.functions.postAggregation(
            ritualId=ritual_id,
            aggregatedTranscript=bytes(aggregated_transcript),
            dkgPublicKey=self.Ritual.G1Point.from_dkg_public_key(public_key),
            decryptionRequestStaticKey=bytes(participant_public_key),
        )
        receipt = self.blockchain.send_transaction(
            contract_function=contract_function,
            transacting_power=transacting_power,
            fire_and_forget=fire_and_forget,
        )
        return receipt

    @contract_api(TRANSACTION)
    def get_ritual_initiation_cost(
        self, providers: List[ChecksumAddress], duration: int
    ) -> Wei:
        result = self.contract.functions.getRitualInitiationCost(
            providers, duration
        ).call()
        return Wei(result)

    @contract_api(TRANSACTION)
    def get_ritual_id_from_public_key(self, public_key: DkgPublicKey) -> int:
        g1_point = self.Ritual.G1Point.from_dkg_public_key(public_key)
        result = self.contract.functions.getRitualIdFromPublicKey(g1_point).call()
        return result

    def get_ritual_public_key(self, ritual_id: int) -> DkgPublicKey:
        if self.get_ritual_status(ritual_id=ritual_id) != self.Ritual.Status.FINALIZED:
            # TODO should we raise here instead?
            return None

        ritual = self.get_ritual(ritual_id=ritual_id)
        if not ritual.public_key:
            return None

        return ritual.public_key.to_dkg_public_key()


class ContractAgency:
    """Where agents live and die."""

    # TODO: Enforce singleton - #1506 - Okay, actually, make this into a module
    __agents: Dict[str, Dict[Type[EthereumContractAgent], EthereumContractAgent]] = dict()

    @classmethod
    def get_agent(
        cls,
        agent_class: Type[types.Agent],
        registry: Optional[ContractRegistry],
        blockchain_endpoint: Optional[str],
        contract_version: Optional[str] = None,
    ) -> types.Agent:
        if not issubclass(agent_class, EthereumContractAgent):
            raise TypeError("Only agent subclasses can be used from the agency.")

        if not blockchain_endpoint:
            raise ValueError(
                "Need to specify a blockchain provider URI in order to get an agent from the ContractAgency"
            )

        if not registry:
            raise ValueError(
                "Need to specify a registry in order to get an agent from the ContractAgency"
            )
        registry_id = registry.id

        try:
            return cast(types.Agent, cls.__agents[registry_id][agent_class])
        except KeyError:
            agent = cast(
                types.Agent,
                agent_class(
                    registry=registry,
                    blockchain_endpoint=blockchain_endpoint,
                ),
            )
            cls.__agents[registry_id] = cls.__agents.get(registry_id, dict())
            cls.__agents[registry_id][agent_class] = agent
            return agent

    @staticmethod
    def _contract_name_to_agent_name(name: str) -> str:
        if name == NUCYPHER_TOKEN_CONTRACT_NAME:
            # TODO: Perhaps rename NucypherTokenAgent
            name = "NucypherToken"
        agent_name = f"{name}Agent"
        return agent_name

    @classmethod
    def get_agent_by_contract_name(
        cls,
        contract_name: str,
        registry: ContractRegistry,
        provider_uri: str,
        contract_version: Optional[str] = None,
    ) -> EthereumContractAgent:
        agent_name: str = cls._contract_name_to_agent_name(name=contract_name)
        agents_module = sys.modules[__name__]
        agent_class: Type[EthereumContractAgent] = getattr(agents_module, agent_name)
        agent: EthereumContractAgent = cls.get_agent(
            agent_class=agent_class,
            registry=registry,
            blockchain_endpoint=provider_uri,
            contract_version=contract_version
        )
        return agent


class WeightedSampler:
    """
    Samples random elements with probabilities proportional to given weights.
    """

    def __init__(self, weighted_elements: Dict[Any, int]):
        if weighted_elements:
            elements, weights = zip(*weighted_elements.items())
        else:
            elements, weights = [], []
        self.totals = list(accumulate(weights))
        self.elements = elements
        self.__length = len(self.totals)

    def sample_no_replacement(self, rng, quantity: int) -> list:
        """
        Samples ``quantity`` of elements from the internal array.
        The probability of an element to appear is proportional
        to the weight provided to the constructor.

        The elements will not repeat; every time an element is sampled its weight is set to 0.
        (does not mutate the object and only applies to the current invocation of the method).
        """

        if quantity == 0:
            return []

        if quantity > len(self):
            raise ValueError("Cannot sample more than the total amount of elements without replacement")

        samples = []

        for i in range(quantity):
            position = rng.randint(0, self.totals[-1] - 1)
            idx = bisect_right(self.totals, position)
            samples.append(self.elements[idx])

            # Adjust the totals so that they correspond
            # to the weight of the element `idx` being set to 0.
            prev_total = self.totals[idx - 1] if idx > 0 else 0
            weight = self.totals[idx] - prev_total
            for j in range(idx, len(self.totals)):
                self.totals[j] -= weight

        self.__length -= quantity

        return samples

    def __len__(self):
        return self.__length


class StakingProvidersReservoir:

    def __init__(self, staking_provider_map: Dict[ChecksumAddress, int]):
        self._sampler = WeightedSampler(staking_provider_map)
        self._rng = random.SystemRandom()

    def __len__(self):
        return len(self._sampler)

    def draw(self, quantity):
        if quantity > len(self):
            raise TACoApplicationAgent.NotEnoughStakingProviders(
                f"Cannot sample {quantity} out of {len(self)} total staking providers"
            )

        return self._sampler.sample_no_replacement(self._rng, quantity)

    def draw_at_most(self, quantity):
        return self.draw(min(quantity, len(self)))
