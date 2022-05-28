"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os
import random
import sys
from bisect import bisect_right
from itertools import accumulate
from typing import Dict, Iterable, List, Tuple, Type, Any, Optional, cast, NamedTuple

from constant_sorrow.constants import (  # type: ignore
    CONTRACT_CALL,
    TRANSACTION,
    CONTRACT_ATTRIBUTE
)
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_checksum_address
from web3.contract import Contract, ContractFunction
from web3.types import Wei, Timestamp, TxReceipt, TxParams

from nucypher.blockchain.eth.constants import (
    ADJUDICATOR_CONTRACT_NAME,
    DISPATCHER_CONTRACT_NAME,
    ETH_ADDRESS_BYTE_LENGTH,
    NUCYPHER_TOKEN_CONTRACT_NAME,
    NULL_ADDRESS,
    SUBSCRIPTION_MANAGER_CONTRACT_NAME,
    PRE_APPLICATION_CONTRACT_NAME
)
from nucypher.blockchain.eth.decorators import contract_api
from nucypher.blockchain.eth.events import ContractEvents
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE,
    NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE
)
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.utils import sha256_digest
from nucypher.types import (
    Agent,
    NuNits,
    StakingProviderInfo,
    TuNits
)
from nucypher.utilities.logging import Logger  # type: ignore


class EthereumContractAgent:
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    contract_name: str = NotImplemented
    _forward_address: bool = True
    _proxy_name: Optional[str] = None
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

    def __init__(self,
                 registry: BaseContractRegistry = None,  # TODO: Consider make it non-optional again. See comment in InstanceAgent.
                 eth_provider_uri: Optional[str] = None,
                 contract: Optional[Contract] = None,
                 transaction_gas: Optional[Wei] = None,
                 contract_version: Optional[str] = None):

        self.log = Logger(self.__class__.__name__)
        self.registry = registry

        self.blockchain = BlockchainInterfaceFactory.get_or_create_interface(eth_provider_uri=eth_provider_uri)

        if not contract:  # Fetch the contract
            contract = self.blockchain.get_contract_by_name(
                registry=registry,
                contract_name=self.contract_name,
                contract_version=contract_version,
                proxy_name=self._proxy_name,
                use_proxy_address=self._forward_address
            )

        self.__contract = contract
        self.events = ContractEvents(contract)
        if not transaction_gas:
            transaction_gas = EthereumContractAgent.DEFAULT_TRANSACTION_GAS_LIMITS['default']
        self.transaction_gas = transaction_gas

        self.log.info("Initialized new {} for {} with {} and {}".format(
            self.__class__.__name__,
            self.contract.address,
            self.blockchain.eth_provider_uri,
            str(self.registry)
        ))

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

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def owner(self) -> Optional[ChecksumAddress]:
        if not self._proxy_name:
            # Only upgradeable + ownable contracts can implement ownership transference.
            return None
        return self.contract.functions.owner().call()


class NucypherTokenAgent(EthereumContractAgent):

    contract_name: str = NUCYPHER_TOKEN_CONTRACT_NAME

    @contract_api(CONTRACT_CALL)
    def get_balance(self, address: ChecksumAddress) -> NuNits:
        """Get the NU balance (in NuNits) of a token holder address, or of this contract address"""
        balance: int = self.contract.functions.balanceOf(address).call()
        return NuNits(balance)

    @contract_api(CONTRACT_CALL)
    def get_allowance(self, owner: ChecksumAddress, spender: ChecksumAddress) -> NuNits:
        """Check the amount of tokens that an owner allowed to a spender"""
        allowance: int = self.contract.functions.allowance(owner, spender).call()
        return NuNits(allowance)

    @contract_api(TRANSACTION)
    def increase_allowance(self,
                           transacting_power: TransactingPower,
                           spender_address: ChecksumAddress,
                           increase: NuNits
                           ) -> TxReceipt:
        """Increase the allowance of a spender address funded by a sender address"""
        contract_function: ContractFunction = self.contract.functions.increaseAllowance(spender_address, increase)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def decrease_allowance(self,
                           transacting_power: TransactingPower,
                           spender_address: ChecksumAddress,
                           decrease: NuNits
                           ) -> TxReceipt:
        """Decrease the allowance of a spender address funded by a sender address"""
        contract_function: ContractFunction = self.contract.functions.decreaseAllowance(spender_address, decrease)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def approve_transfer(self,
                         amount: NuNits,
                         spender_address: ChecksumAddress,
                         transacting_power: TransactingPower
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
    def transfer(self, amount: NuNits, target_address: ChecksumAddress, transacting_power: TransactingPower) -> TxReceipt:
        """Transfer an amount of tokens from the sender address to the target address."""
        contract_function: ContractFunction = self.contract.functions.transfer(target_address, amount)
        receipt: TxReceipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                              transacting_power=transacting_power)
        return receipt

    @contract_api(TRANSACTION)
    def approve_and_call(self,
                         amount: NuNits,
                         target_address: ChecksumAddress,
                         transacting_power: TransactingPower,
                         call_data: bytes = b'',
                         gas_limit: Optional[Wei] = None
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
    # TODO: A future deployment of SubscriptionManager may have a proxy.
    #  _proxy_name: str = DISPATCHER_CONTRACT_NAME

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


class AdjudicatorAgent(EthereumContractAgent):

    contract_name: str = ADJUDICATOR_CONTRACT_NAME
    _proxy_name: str = DISPATCHER_CONTRACT_NAME

    @contract_api(TRANSACTION)
    def evaluate_cfrag(self, evidence, transacting_power: TransactingPower) -> TxReceipt:
        """Submits proof that a worker created wrong CFrag"""
        payload: TxParams = {'gas': Wei(500_000)}  # TODO TransactionFails unless gas is provided.
        contract_function: ContractFunction = self.contract.functions.evaluateCFrag(*evidence.evaluation_arguments())
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   transacting_power=transacting_power,
                                                   payload=payload)
        return receipt

    @contract_api(CONTRACT_CALL)
    def was_this_evidence_evaluated(self, evidence) -> bool:
        data_hash: bytes = sha256_digest(evidence.task.capsule, evidence.task.cfrag)
        result: bool = self.contract.functions.evaluatedCFrags(data_hash).call()
        return result

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def staking_escrow_contract(self) -> ChecksumAddress:
        return self.contract.functions.escrow().call()

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def hash_algorithm(self) -> int:
        return self.contract.functions.hashAlgorithm().call()

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def base_penalty(self) -> int:
        return self.contract.functions.basePenalty().call()

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def penalty_history_coefficient(self) -> int:
        return self.contract.functions.penaltyHistoryCoefficient().call()

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def percentage_penalty_coefficient(self) -> int:
        return self.contract.functions.percentagePenaltyCoefficient().call()

    @property  # type: ignore
    @contract_api(CONTRACT_ATTRIBUTE)
    def reward_coefficient(self) -> int:
        return self.contract.functions.rewardCoefficient().call()

    @contract_api(CONTRACT_CALL)
    def penalty_history(self, staker_address: str) -> int:
        return self.contract.functions.penaltyHistory(staker_address).call()

    @contract_api(CONTRACT_CALL)
    def slashing_parameters(self) -> Tuple[int, ...]:
        parameter_signatures = (
            'hashAlgorithm',                    # Hashing algorithm
            'basePenalty',                      # Base for the penalty calculation
            'penaltyHistoryCoefficient',        # Coefficient for calculating the penalty depending on the history
            'percentagePenaltyCoefficient',     # Coefficient for calculating the percentage penalty
            'rewardCoefficient',                # Coefficient for calculating the reward
        )

        def _call_function_by_name(name: str) -> int:
            return getattr(self.contract.functions, name)().call()

        staking_parameters = tuple(map(_call_function_by_name, parameter_signatures))
        return staking_parameters


class PREApplicationAgent(EthereumContractAgent):

    contract_name: str = PRE_APPLICATION_CONTRACT_NAME

    DEFAULT_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE = int(os.environ.get(NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE, default=30))
    DEFAULT_PROVIDERS_PAGINATION_SIZE = int(os.environ.get(NUCYPHER_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE, default=1000))

    class NotEnoughStakingProviders(Exception):
        pass

    class OperatorInfo(NamedTuple):
        address: ChecksumAddress
        confirmed: bool
        start_timestamp: Timestamp

    @contract_api(CONTRACT_CALL)
    def get_min_authorization(self) -> int:
        result = self.contract.functions.minAuthorization().call()
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
    def get_staking_provider_info(self, staking_provider: ChecksumAddress) -> StakingProviderInfo:
        # remove reserved fields
        info: list = self.contract.functions.stakingProviderInfo(staking_provider).call()
        return StakingProviderInfo(*info[0:3])

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
    def get_all_active_staking_providers(self, pagination_size: Optional[int] = None) -> Tuple[TuNits, Dict[ChecksumAddress, TuNits]]:

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

        typed_staking_providers = {checksum_address(address): TuNits(authorized_tokens)
                                   for address, authorized_tokens in staking_providers.items()}

        return TuNits(n_tokens), typed_staking_providers

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
            raise self.NotEnoughStakingProviders(f'There are no locked tokens.')

        return StakingProvidersReservoir(stake_provider_map)

    #
    # Transactions
    #

    @contract_api(TRANSACTION)
    def confirm_operator_address(self, transacting_power: TransactingPower, fire_and_forget: bool = True) -> TxReceipt:
        """Confirm the sender's account as a operator"""
        contract_function: ContractFunction = self.contract.functions.confirmOperatorAddress()
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   transacting_power=transacting_power,
                                                   fire_and_forget=fire_and_forget
                                                   )
        return receipt

    @contract_api(TRANSACTION)
    def bond_operator(self, staking_provider: ChecksumAddress, operator: ChecksumAddress, transacting_power: TransactingPower) -> TxReceipt:
        """For use by threshold operator accounts only."""
        contract_function: ContractFunction = self.contract.functions.bondOperator(staking_provider, operator)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   transacting_power=transacting_power)
        return receipt


class ContractAgency:
    """Where agents live and die."""

    # TODO: Enforce singleton - #1506 - Okay, actually, make this into a module
    __agents: Dict[str, Dict[Type[EthereumContractAgent], EthereumContractAgent]] = dict()

    @classmethod
    def get_agent(cls,
                  agent_class: Type[Agent],
                  registry: Optional[BaseContractRegistry] = None,
                  eth_provider_uri: Optional[str] = None,
                  contract_version: Optional[str] = None
                  ) -> Agent:

        if not issubclass(agent_class, EthereumContractAgent):
            raise TypeError(f"Only agent subclasses can be used from the agency.")

        if not registry:
            if len(cls.__agents) == 1:
                registry_id = list(cls.__agents.keys()).pop()
            else:
                raise ValueError("Need to specify a registry in order to get an agent from the ContractAgency")
        else:
            registry_id = registry.id
        try:
            return cast(Agent, cls.__agents[registry_id][agent_class])
        except KeyError:
            agent = cast(Agent, agent_class(registry=registry, eth_provider_uri=eth_provider_uri, contract_version=contract_version))
            cls.__agents[registry_id] = cls.__agents.get(registry_id, dict())
            cls.__agents[registry_id][agent_class] = agent
            return agent

    @staticmethod
    def _contract_name_to_agent_name(name: str) -> str:
        if name == NUCYPHER_TOKEN_CONTRACT_NAME:
            # TODO: Perhaps rename NucypherTokenAgent
            name = "NucypherToken"
        if name == PRE_APPLICATION_CONTRACT_NAME:
            name = "PREApplication"  # TODO not needed once full PRE Application is used
        agent_name = f"{name}Agent"
        return agent_name

    @classmethod
    def get_agent_by_contract_name(cls,
                                   contract_name: str,
                                   registry: BaseContractRegistry,
                                   eth_provider_uri: Optional[str] = None,
                                   contract_version: Optional[str] = None
                                   ) -> EthereumContractAgent:
        agent_name: str = cls._contract_name_to_agent_name(name=contract_name)
        agents_module = sys.modules[__name__]
        agent_class: Type[EthereumContractAgent] = getattr(agents_module, agent_name)
        agent: EthereumContractAgent = cls.get_agent(
            agent_class=agent_class,
            registry=registry,
            eth_provider_uri=eth_provider_uri,
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
            raise PREApplicationAgent.NotEnoughStakingProviders(f'Cannot sample {quantity} out of {len(self)} total staking providers')

        return self._sampler.sample_no_replacement(self._rng, quantity)

    def draw_at_most(self, quantity):
        return self.draw(min(quantity, len(self)))
