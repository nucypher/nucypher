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

import importlib
import math
import random
from typing import Generator, List, Tuple, Union

from constant_sorrow.constants import NO_CONTRACT_AVAILABLE
from eth_utils.address import to_checksum_address
from eth_tester.exceptions import TransactionFailed
from twisted.logger import Logger
from web3.contract import Contract

from nucypher.blockchain.eth.constants import (
    DISPATCHER_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME,
    POLICY_MANAGER_CONTRACT_NAME,
    PREALLOCATION_ESCROW_CONTRACT_NAME,
    STAKING_INTERFACE_CONTRACT_NAME,
    STAKING_INTERFACE_ROUTER_CONTRACT_NAME,
    ADJUDICATOR_CONTRACT_NAME,
    NUCYPHER_TOKEN_CONTRACT_NAME,
    MULTISIG_CONTRACT_NAME,
    SEEDER_CONTRACT_NAME,
    ETH_ADDRESS_BYTE_LENGTH
)
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.events import ContractEvents
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import AllocationRegistry, BaseContractRegistry
from nucypher.blockchain.eth.utils import epoch_to_period
from nucypher.crypto.api import sha256_digest


class ContractAgency:
    # TODO: Enforce singleton - #1506

    __agents = dict()

    @classmethod
    def get_agent(cls,
                  agent_class,
                  registry: BaseContractRegistry,
                  provider_uri: str = None,
                  ) -> 'EthereumContractAgent':

        if not issubclass(agent_class, EthereumContractAgent):
            raise TypeError(f"Only agent subclasses can be used from the agency.")
        registry_id = registry.id
        try:
            return cls.__agents[registry_id][agent_class]
        except KeyError:
            agent = agent_class(registry=registry, provider_uri=provider_uri)
            cls.__agents[registry_id] = cls.__agents.get(registry_id, dict())
            cls.__agents[registry_id][agent_class] = agent
            return agent

    @classmethod
    def get_agent_by_contract_name(cls,
                                   contract_name: str,
                                   registry: BaseContractRegistry,
                                   provider_uri: str = None,
                                   ) -> 'EthereumContractAgent':

        if contract_name == NUCYPHER_TOKEN_CONTRACT_NAME:  # TODO: Perhaps rename NucypherTokenAgent
            contract_name = "NucypherToken"

        agent_name = f"{contract_name}Agent"
        agents_module = importlib.import_module("nucypher.blockchain.eth.agents")  # TODO: Is there a programmatic way to get the module?
        agent_class = getattr(agents_module, agent_name)
        agent = cls.get_agent(agent_class=agent_class, registry=registry, provider_uri=provider_uri)
        return agent


class EthereumContractAgent:
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    registry_contract_name = NotImplemented
    _forward_address = True
    _proxy_name = None

    # TODO - #842: Gas Management
    DEFAULT_TRANSACTION_GAS_LIMITS = {}

    class ContractNotDeployed(Exception):
        pass

    def __init__(self,
                 registry: BaseContractRegistry,
                 provider_uri: str = None,
                 contract: Contract = None,
                 transaction_gas: int = None
                 ) -> None:

        self.log = Logger(self.__class__.__name__)

        self.registry = registry

        # NOTE: Entry-point for multi-provider support
        self.blockchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=provider_uri)

        if contract is None:  # Fetch the contract
            contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                            contract_name=self.registry_contract_name,
                                                            proxy_name=self._proxy_name,
                                                            use_proxy_address=self._forward_address)
        self.__contract = contract
        self.events = ContractEvents(contract)
        if not transaction_gas:
            transaction_gas = EthereumContractAgent.DEFAULT_TRANSACTION_GAS_LIMITS
        self.transaction_gas = transaction_gas

        super().__init__()
        self.log.info("Initialized new {} for {} with {} and {}".format(self.__class__.__name__,
                                                                        self.contract.address,
                                                                        self.blockchain.provider_uri,
                                                                        self.registry))

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(registry={}, contract={})"
        return r.format(class_name, self.registry, self.registry_contract_name)

    def __eq__(self, other):
        return bool(self.contract.address == other.contract.address)

    @property
    def contract(self):
        return self.__contract

    @property
    def contract_address(self):
        return self.__contract.address

    @property
    def contract_name(self) -> str:
        return self.registry_contract_name

    @property
    def owner(self):
        if not self._proxy_name:
            # Only upgradeable + ownable contracts can implement ownership transference.
            return None
        return self.contract.functions.owner().call()

    @validate_checksum_address
    def transfer_ownership(self, sender_address: str, checksum_address: str, transaction_gas_limit: int = None) -> dict:
        contract_function = self.contract.functions.transferOwnership(checksum_address)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address,
                                                   transaction_gas_limit=transaction_gas_limit)
        return receipt


class NucypherTokenAgent(EthereumContractAgent):

    registry_contract_name = NUCYPHER_TOKEN_CONTRACT_NAME

    def get_balance(self, address: str = None) -> int:
        """Get the NU balance (in NuNits) of a token holder address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()

    @validate_checksum_address
    def increase_allowance(self, sender_address: str, target_address: str, increase: int):
        contract_function = self.contract.functions.increaseAllowance(target_address, increase)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address)
        return receipt

    @validate_checksum_address
    def approve_transfer(self, amount: int, target_address: str, sender_address: str):
        """Approve the transfer of tokens from the sender address to the target address."""
        payload = {'gas': 500_000}  # TODO #842: gas needed for use with geth.
        contract_function = self.contract.functions.approve(target_address, amount)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   payload=payload,
                                                   sender_address=sender_address)
        return receipt

    @validate_checksum_address
    def transfer(self, amount: int, target_address: str, sender_address: str):
        contract_function = self.contract.functions.transfer(target_address, amount)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=sender_address)
        return receipt

    @validate_checksum_address
    def approve_and_call(self,
                         amount: int,
                         target_address: str,
                         sender_address: str,
                         call_data: bytes = b'',
                         gas_limit: int = None):
        payload = None
        if gas_limit:  # TODO: Gas management - #842
            payload = {'gas': gas_limit}

        approve_and_call = self.contract.functions.approveAndCall(target_address, amount, call_data)
        approve_and_call_receipt = self.blockchain.send_transaction(contract_function=approve_and_call,
                                                                    sender_address=sender_address,
                                                                    payload=payload)
        return approve_and_call_receipt


class StakingEscrowAgent(EthereumContractAgent):

    registry_contract_name = STAKING_ESCROW_CONTRACT_NAME
    _proxy_name = DISPATCHER_CONTRACT_NAME

    DEFAULT_PAGINATION_SIZE = 30    # TODO: Use dynamic pagination size (see #1424)

    class NotEnoughStakers(Exception):
        pass

    #
    # Staker Network Status
    #

    def get_staker_population(self) -> int:
        """Returns the number of stakers on the blockchain"""
        return self.contract.functions.getStakersLength().call()

    def get_current_period(self) -> int:
        """Returns the current period"""
        return self.contract.functions.getCurrentPeriod().call()

    def get_stakers(self) -> List[str]:
        """Returns a list of stakers"""
        num_stakers = self.get_staker_population()
        stakers = [self.contract.functions.stakers(i).call() for i in range(num_stakers)]
        return stakers

    def partition_stakers_by_activity(self) -> Tuple[List[str], List[str], List[str]]:
        """Returns three lists of stakers depending on how they confirmed activity:
        The first list contains stakers that already confirmed next period.
        The second, stakers that confirmed for current period but haven't confirmed next yet.
        The third contains stakers that have missed activity confirmation before current period"""

        num_stakers = self.get_staker_population()
        current_period = self.get_current_period()

        active_stakers, pending_stakers, missing_stakers = [], [], []
        for i in range(num_stakers):
            staker = self.contract.functions.stakers(i).call()
            last_active_period = self.get_last_active_period(staker)
            if last_active_period == current_period + 1:
                active_stakers.append(staker)
            elif last_active_period == current_period:
                pending_stakers.append(staker)
            else:
                missing_stakers.append(staker)

        return active_stakers, pending_stakers, missing_stakers

    def get_all_active_stakers(self, periods: int, pagination_size: int = None) -> Tuple[int, List[str]]:
        """Only stakers which confirmed the current period (in the previous period) are used."""
        if not periods > 0:
            raise ValueError("Period must be > 0")

        if pagination_size is None:
            pagination_size = StakingEscrowAgent.DEFAULT_PAGINATION_SIZE if self.blockchain.is_light else 0
        elif pagination_size < 0:
            raise ValueError("Pagination size must be >= 0")

        if pagination_size > 0:
            num_stakers = self.get_staker_population()
            start_index = 0
            n_tokens = 0
            stakers = list()
            while start_index < num_stakers:
                temp_locked_tokens, temp_stakers = \
                    self.contract.functions.getActiveStakers(periods, start_index, pagination_size).call()
                n_tokens += temp_locked_tokens
                stakers += temp_stakers
                start_index += pagination_size
        else:
            n_tokens, stakers = self.contract.functions.getActiveStakers(periods, 0, 0).call()

        # Sanitize output of getActiveStakers: stakers' addresses are returned as uint256, but we need addresses
        for i in range(len(stakers)):
            stakers[i][0] = to_checksum_address(stakers[i][0].to_bytes(ETH_ADDRESS_BYTE_LENGTH, 'big'))

        return n_tokens, stakers

    def get_all_locked_tokens(self, periods: int, pagination_size: int = None) -> int:
        all_locked_tokens, _stakers = self.get_all_active_stakers(periods=periods, pagination_size=pagination_size)
        return all_locked_tokens

    #
    # StakingEscrow Contract API
    #

    def get_global_locked_tokens(self, at_period: int = None) -> int:
        """
        Gets the number of locked tokens for *all* stakers that have
        confirmed activity for the specified period.

        `at_period` values can be any valid period number past, present, or future:

            PAST - Calling this function with an `at_period` value in the past will return the number
            of locked tokens whose worker activity was confirmed for that past period.

            PRESENT - This is the default value, when no `at_period` value is provided.

            FUTURE - Calling this function with an `at_period` value greater than
            the current period + 1 (next period), will result in a zero return value
            because activity cannot be confirmed beyond the next period.

        Returns an amount of NuNits.
        """
        if at_period is None:
            # Get the current period on-chain by default.
            at_period = self.contract.functions.getCurrentPeriod().call()
        return self.contract.functions.lockedPerPeriod(at_period).call()

    @validate_checksum_address
    def get_staker_info(self, staker_address: str):
        return self.contract.functions.stakerInfo(staker_address).call()

    @validate_checksum_address
    def get_locked_tokens(self, staker_address: str, periods: int = 0) -> int:
        """
        Returns the amount of tokens this staker has locked
        for a given duration in periods measured from the current period forwards.
        """
        if periods < 0:
            raise ValueError(f"Periods value must not be negative, Got '{periods}'.")
        return self.contract.functions.getLockedTokens(staker_address, periods).call()

    @validate_checksum_address
    def owned_tokens(self, staker_address: str) -> int:
        """
        Returns all tokens that belong to staker_address, including locked, unlocked and rewards.
        """
        return self.contract.functions.getAllTokens(staker_address).call()

    @validate_checksum_address
    def get_substake_info(self, staker_address: str, stake_index: int) -> Tuple[int, int, int]:
        first_period, *others, locked_value = self.contract.functions.getSubStakeInfo(staker_address, stake_index).call()
        last_period = self.contract.functions.getLastPeriodOfSubStake(staker_address, stake_index).call()
        return first_period, last_period, locked_value

    @validate_checksum_address
    def get_raw_substake_info(self, staker_address: str, stake_index: int) -> Tuple[int, int, int, int]:
        result = self.contract.functions.getSubStakeInfo(staker_address, stake_index).call()
        first_period, last_period, periods, locked = result
        return first_period, last_period, periods, locked

    @validate_checksum_address
    def get_all_stakes(self, staker_address: str):
        stakes_length = self.contract.functions.getSubStakesLength(staker_address).call()
        if stakes_length == 0:
            return iter(())  # Empty iterable, There are no stakes
        for stake_index in range(stakes_length):
            yield self.get_substake_info(staker_address=staker_address, stake_index=stake_index)

    @validate_checksum_address
    def deposit_tokens(self, amount: int, lock_periods: int, sender_address: str):
        """Send tokens to the escrow from the staker's address"""
        contract_function = self.contract.functions.deposit(amount, lock_periods)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address)
        return receipt

    @validate_checksum_address
    def divide_stake(self, staker_address: str, stake_index: int, target_value: int, periods: int) -> dict:
        contract_function = self.contract.functions.divideStake(stake_index, target_value, periods)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt

    @validate_checksum_address
    def prolong_stake(self, staker_address: str, stake_index: int, periods: int) -> dict:
        contract_function = self.contract.functions.prolongStake(stake_index, periods)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt

    @validate_checksum_address
    def get_last_active_period(self, staker_address: str) -> int:
        period = self.contract.functions.getLastActivePeriod(staker_address).call()
        return int(period)

    @validate_checksum_address
    def get_worker_from_staker(self, staker_address: str) -> str:
        worker = self.contract.functions.getWorkerFromStaker(staker_address).call()
        return to_checksum_address(worker)

    @validate_checksum_address
    def get_staker_from_worker(self, worker_address: str) -> str:
        staker = self.contract.functions.getStakerFromWorker(worker_address).call()
        return to_checksum_address(staker)

    @validate_checksum_address
    def set_worker(self, staker_address: str, worker_address: str):
        contract_function = self.contract.functions.setWorker(worker_address)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt

    @validate_checksum_address
    def release_worker(self, staker_address: str):
        return self.set_worker(staker_address=staker_address, worker_address=BlockchainInterface.NULL_ADDRESS)

    @validate_checksum_address
    def confirm_activity(self, worker_address: str):
        """
        For each period that the worker confirms activity, the staker is rewarded.
        """
        contract_function = self.contract.functions.confirmActivity()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=worker_address)
        return receipt

    @validate_checksum_address
    def mint(self, staker_address: str):
        """
        Computes reward tokens for the staker's account;
        This is only used to calculate the reward for the final period of a stake,
        when you intend to withdraw 100% of tokens.
        """
        contract_function = self.contract.functions.mint()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt

    @validate_checksum_address
    def calculate_staking_reward(self, staker_address: str) -> int:
        token_amount = self.owned_tokens(staker_address)
        staked_amount = max(self.contract.functions.getLockedTokens(staker_address, 0).call(),
                            self.contract.functions.getLockedTokens(staker_address, 1).call())
        reward_amount = token_amount - staked_amount
        return reward_amount

    @validate_checksum_address
    def collect_staking_reward(self, staker_address: str):
        """Withdraw tokens rewarded for staking."""
        reward_amount = self.calculate_staking_reward(staker_address=staker_address)
        from nucypher.blockchain.eth.token import NU
        self.log.debug(f"Withdrawing staking reward ({NU.from_nunits(reward_amount)}) to {staker_address}")
        return self.withdraw(staker_address=staker_address, amount=reward_amount)

    @validate_checksum_address
    def withdraw(self, staker_address: str, amount: int):
        """Withdraw tokens"""
        payload = {'gas': 500_000}  # TODO: #842 Gas Management
        contract_function = self.contract.functions.withdraw(amount)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   payload=payload,
                                                   sender_address=staker_address)
        return receipt

    @validate_checksum_address
    def is_restaking(self, staker_address: str) -> bool:
        staker_info = self.get_staker_info(staker_address)
        restake_flag = not bool(staker_info[3])  # TODO: #1348 Use constant or enum
        return restake_flag

    @validate_checksum_address
    def is_restaking_locked(self, staker_address: str) -> bool:
        return self.contract.functions.isReStakeLocked(staker_address).call()

    @validate_checksum_address
    def set_restaking(self, staker_address: str, value: bool) -> dict:
        """
        Enable automatic restaking for a fixed duration of lock periods.
        If set to True, then all staking rewards will be automatically added to locked stake.
        """
        contract_function = self.contract.functions.setReStake(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=staker_address)
        # TODO: Handle ReStakeSet event (see #1193)
        return receipt

    @validate_checksum_address
    def lock_restaking(self, staker_address: str, release_period: int) -> dict:
        contract_function = self.contract.functions.lockReStake(release_period)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=staker_address)
        # TODO: Handle ReStakeLocked event (see #1193)
        return receipt

    @validate_checksum_address
    def get_restake_unlock_period(self, staker_address: str) -> int:
        staker_info = self.get_staker_info(staker_address)
        restake_unlock_period = int(staker_info[4])  # TODO: #1348 Use constant or enum
        return restake_unlock_period

    @validate_checksum_address
    def is_winding_down(self, staker_address: str) -> bool:
        staker_info = self.get_staker_info(staker_address)
        winddown_flag = bool(staker_info[10])  # TODO: #1348 Use constant or enum
        return winddown_flag

    @validate_checksum_address
    def set_winding_down(self, staker_address: str, value: bool) -> dict:
        """
        Enable wind down for stake.
        If set to True, then stakes duration will decrease in each period with `confirmActivity()`.
        """
        contract_function = self.contract.functions.setWindDown(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=staker_address)
        # TODO: Handle WindDownSet event (see #1193)
        return receipt

    def staking_parameters(self) -> Tuple:
        parameter_signatures = (
            # Period
            'secondsPerPeriod',  # Seconds in single period

            # Coefficients
            'miningCoefficient',         # Staking coefficient (k2)
            'lockedPeriodsCoefficient',  # Locked periods coefficient (k1)
            'rewardedPeriods',           # Max periods that will be additionally rewarded (awarded_periods)

            # Constraints
            'minLockedPeriods',          # Min amount of periods during which tokens can be locked
            'minAllowableLockedTokens',  # Min amount of tokens that can be locked
            'maxAllowableLockedTokens',  # Max amount of tokens that can be locked
            'minWorkerPeriods'           # Min amount of periods while a worker can't be changed
        )

        def _call_function_by_name(name: str):
            return getattr(self.contract.functions, name)().call()

        staking_parameters = tuple(map(_call_function_by_name, parameter_signatures))
        return staking_parameters

    #
    # Contract Utilities
    #

    def swarm(self) -> Union[Generator[str, None, None], Generator[str, None, None]]:
        """
        Returns an iterator of all staker addresses via cumulative sum, on-network.

        Staker addresses are returned in the order in which they registered with the StakingEscrow contract's ledger

        """

        for index in range(self.get_staker_population()):
            staker_address = self.contract.functions.stakers(index).call()
            yield staker_address

    def sample(self,
               quantity: int,
               duration: int,
               additional_ursulas:float = 1.5,
               attempts: int = 5,
               pagination_size: int = None
               ) -> List[str]:
        """
        Select n random Stakers, according to their stake distribution.

        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.

        See full diagram here: https://github.com/nucypher/kms-whitepaper/blob/master/pdf/miners-ruler.pdf

        This method implements the Probability Proportional to Size (PPS) sampling algorithm.
        In few words, the algorithm places in a line all active stakes that have locked tokens for
        at least `duration` periods; a staker is selected if an input point is within its stake.
        For example:

        Stakes: |----- S0 ----|--------- S1 ---------|-- S2 --|---- S3 ---|-S4-|----- S5 -----|
        Points: ....R0.......................R1..................R2...............R3...........

        In this case, Stakers 0, 1, 3 and 5 will be selected.

        Only stakers which confirmed the current period (in the previous period) are used.
        """

        system_random = random.SystemRandom()
        n_tokens, stakers = self.get_all_active_stakers(periods=duration, pagination_size=pagination_size)
        if n_tokens == 0:
            raise self.NotEnoughStakers('There are no locked tokens for duration {}.'.format(duration))

        sample_size = quantity
        for _ in range(attempts):
            sample_size = math.ceil(sample_size * additional_ursulas)
            points = sorted(system_random.randrange(n_tokens) for _ in range(sample_size))
            self.log.debug(f"Sampling {sample_size} stakers with random points: {points}")

            addresses = set()

            point_index = 0
            sum_of_locked_tokens = 0
            staker_index = 0
            stakers_len = len(stakers)
            while staker_index < stakers_len and point_index < sample_size:
                current_staker = stakers[staker_index][0]
                staker_tokens = stakers[staker_index][1]
                next_sum_value = sum_of_locked_tokens + staker_tokens

                point = points[point_index]
                if sum_of_locked_tokens <= point < next_sum_value:
                    addresses.add(to_checksum_address(current_staker))
                    point_index += 1
                else:
                    staker_index += 1
                    sum_of_locked_tokens = next_sum_value

            self.log.debug(f"Sampled {len(addresses)} stakers: {list(addresses)}")
            if len(addresses) >= quantity:
                return system_random.sample(addresses, quantity)

        raise self.NotEnoughStakers('Selection failed after {} attempts'.format(attempts))

    def get_completed_work(self, bidder_address: str):
        total_completed_work = self.contract.functions.getCompletedWork(bidder_address).call()
        return total_completed_work

    @validate_checksum_address
    def get_missing_confirmations(self, checksum_address: str) -> int:
        # TODO: Move this up one layer, since it utilizes a combination of contract API methods.
        last_confirmed_period = self.get_last_active_period(checksum_address)
        current_period = self.get_current_period()
        missing_confirmations = current_period - last_confirmed_period
        if missing_confirmations in (0, -1):
            result = 0
        elif last_confirmed_period == 0:  # never confirmed
            stakes = list(self.get_all_stakes(staker_address=checksum_address))
            initial_staking_period = min(stakes, key=lambda s: s[0])[0]
            result = current_period - initial_staking_period
        else:
            result = missing_confirmations
        return result


class PolicyManagerAgent(EthereumContractAgent):

    registry_contract_name = POLICY_MANAGER_CONTRACT_NAME
    _proxy_name = DISPATCHER_CONTRACT_NAME

    @validate_checksum_address
    def create_policy(self,
                      policy_id: str,
                      author_address: str,
                      value: int,
                      end_timestamp: int,
                      node_addresses: List[str],
                      owner_address: str = None):

        owner_address = owner_address or author_address
        payload = {'value': value}
        contract_function = self.contract.functions.createPolicy(policy_id,
                                                                 owner_address,
                                                                 end_timestamp,
                                                                 node_addresses)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   payload=payload,
                                                   sender_address=author_address)  # TODO: Gas management - #842
        return receipt

    def fetch_policy(self, policy_id: str) -> list:
        """Fetch raw stored blockchain data regarding the policy with the given policy ID"""
        blockchain_record = self.contract.functions.policies(policy_id).call()
        return blockchain_record

    def fetch_arrangement_addresses_from_policy_txid(self, txhash, timeout=600):
        # TODO: Won't it be great when this is impossible?  #1274
        _receipt = self.blockchain.wait_for_receipt(txhash, timeout=timeout)
        transaction = self.blockchain.client.w3.eth.getTransaction(txhash)
        _signature, parameters = self.contract.decode_function_input(transaction.data)
        return parameters['_nodes']

    @validate_checksum_address
    def revoke_policy(self, policy_id: bytes, author_address: str):
        """Revoke by arrangement ID; Only the policy's author_address can revoke the policy."""
        contract_function = self.contract.functions.revokePolicy(policy_id)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=author_address)
        return receipt

    @validate_checksum_address
    def collect_policy_reward(self, collector_address: str, staker_address: str):
        """Collect rewarded ETH"""
        contract_function = self.contract.functions.withdraw(collector_address)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt

    def fetch_policy_arrangements(self, policy_id):
        record_count = self.contract.functions.getArrangementsLength(policy_id).call()
        for index in range(record_count):
            arrangement = self.contract.functions.getArrangementInfo(policy_id, index).call()
            yield arrangement

    @validate_checksum_address
    def revoke_arrangement(self, policy_id: str, node_address: str, author_address: str):
        contract_function = self.contract.functions.revokeArrangement(policy_id, node_address)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=author_address)
        return receipt

    @validate_checksum_address
    def calculate_refund(self, policy_id: str, author_address: str):
        contract_function = self.contract.functions.calculateRefundValue(policy_id)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=author_address)
        return receipt

    @validate_checksum_address
    def collect_refund(self, policy_id: str, author_address: str):
        contract_function = self.contract.functions.refund(policy_id)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=author_address)
        return receipt

    @validate_checksum_address
    def get_reward_amount(self, staker_address: str) -> int:
        reward_amount = self.contract.functions.nodes(staker_address).call()[0]
        return reward_amount

    def get_min_reward_rate_range(self) -> Tuple[int, int, int]:
        minimum, default, maximum = self.contract.functions.minRewardRateRange().call()
        return minimum, default, maximum

    @validate_checksum_address
    def get_min_reward_rate(self, staker_address: str) -> int:
        min_rate = self.contract.functions.getMinRewardRate(staker_address).call()
        return min_rate

    @validate_checksum_address
    def get_raw_min_reward_rate(self, staker_address: str) -> int:
        min_rate = self.contract.functions.nodes(staker_address).call()[3]
        return min_rate

    @validate_checksum_address
    def set_min_reward_rate(self, staker_address: str, min_rate: int):
        contract_function = self.contract.functions.setMinRewardRate(min_rate)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=staker_address)
        return receipt


class PreallocationEscrowAgent(EthereumContractAgent):

    registry_contract_name = PREALLOCATION_ESCROW_CONTRACT_NAME
    _proxy_name = NotImplemented
    _forward_address = False
    __allocation_registry = AllocationRegistry

    class StakingInterfaceAgent(EthereumContractAgent):
        registry_contract_name = STAKING_INTERFACE_CONTRACT_NAME
        _proxy_name = STAKING_INTERFACE_ROUTER_CONTRACT_NAME
        _forward_address = False

        @validate_checksum_address
        def _generate_beneficiary_agency(self, principal_address: str):
            contract = self.blockchain.client.get_contract(address=principal_address, abi=self.contract.abi)
            return contract

    def __init__(self,
                 beneficiary: str,
                 registry: BaseContractRegistry,
                 allocation_registry: AllocationRegistry = None,
                 *args, **kwargs):

        self.__allocation_registry = allocation_registry or self.__allocation_registry()
        self.__beneficiary = beneficiary
        self.__principal_contract = NO_CONTRACT_AVAILABLE
        self.__interface_agent = NO_CONTRACT_AVAILABLE

        # Sets the above
        self.__read_principal()
        self.__read_interface(registry)

        super().__init__(contract=self.principal_contract, registry=registry, *args, **kwargs)

    def __read_interface(self, registry: BaseContractRegistry):
        self.__interface_agent = self.StakingInterfaceAgent(registry=registry)
        contract = self.__interface_agent._generate_beneficiary_agency(principal_address=self.principal_contract.address)
        self.__interface_agent = contract

    @validate_checksum_address
    def __fetch_principal_contract(self, contract_address: str = None) -> None:
        """Fetch the PreallocationEscrow deployment directly from the AllocationRegistry."""
        if contract_address is not None:
            contract_data = self.__allocation_registry.search(contract_address=contract_address)
        else:
            contract_data = self.__allocation_registry.search(beneficiary_address=self.beneficiary)
        address, abi = contract_data
        blockchain = BlockchainInterfaceFactory.get_interface()
        principal_contract = blockchain.client.get_contract(abi=abi, address=address, ContractFactoryClass=Contract)
        self.__principal_contract = principal_contract

    def __set_owner(self) -> None:
        self.__beneficiary = self.owner

    @validate_checksum_address
    def __read_principal(self, contract_address: str = None) -> None:
        self.__fetch_principal_contract(contract_address=contract_address)
        self.__set_owner()

    @property
    def owner(self) -> str:
        owner = self.principal_contract.functions.owner().call()
        return owner

    @property
    def beneficiary(self) -> str:
        return self.__beneficiary

    @property
    def interface_contract(self) -> Contract:
        if self.__interface_agent is NO_CONTRACT_AVAILABLE:
            raise RuntimeError("{} not available".format(self.registry_contract_name))
        return self.__interface_agent

    @property
    def principal_contract(self) -> Contract:
        """Directly reference the beneficiary's deployed contract instead of the interface contracts's ABI"""
        if self.__principal_contract is NO_CONTRACT_AVAILABLE:
            raise RuntimeError("{} not available".format(self.registry_contract_name))
        return self.__principal_contract

    @property
    def initial_locked_amount(self) -> int:
        return self.principal_contract.functions.lockedValue().call()

    @property
    def available_balance(self) -> int:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, self.registry)
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, self.registry)

        overall_balance = token_agent.get_balance(self.principal_contract.address)
        seconds_per_period = staking_agent.contract.functions.secondsPerPeriod().call()
        current_period = staking_agent.get_current_period()
        end_lock_period = epoch_to_period(self.end_timestamp, seconds_per_period=seconds_per_period)

        available_balance = overall_balance
        if current_period <= end_lock_period:
            staked_tokens = staking_agent.get_locked_tokens(staker_address=self.principal_contract.address,
                                                            periods=end_lock_period - current_period)
            if self.unvested_tokens > staked_tokens:
                # The staked amount is deducted from the locked amount
                available_balance -= self.unvested_tokens - staked_tokens

        return available_balance

    @property
    def unvested_tokens(self) -> int:
        return self.principal_contract.functions.getLockedTokens().call()

    @property
    def end_timestamp(self) -> int:
        return self.principal_contract.functions.endLockTimestamp().call()

    def lock(self, amount: int, periods: int):
        contract_function = self.__interface_agent.functions.lock(amount, periods)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def withdraw_tokens(self, value: int):
        contract_function = self.principal_contract.functions.withdrawTokens(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def withdraw_eth(self):
        contract_function = self.principal_contract.functions.withdrawETH()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def deposit_as_staker(self, amount: int, lock_periods: int):
        contract_function = self.__interface_agent.functions.depositAsStaker(amount, lock_periods)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def withdraw_as_staker(self, value: int):
        contract_function = self.__interface_agent.functions.withdrawAsStaker(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    @validate_checksum_address
    def set_worker(self, worker_address: str):
        contract_function = self.__interface_agent.functions.setWorker(worker_address)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def release_worker(self):
        receipt = self.set_worker(worker_address=BlockchainInterface.NULL_ADDRESS)
        return receipt

    def mint(self):
        contract_function = self.__interface_agent.functions.mint()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def collect_policy_reward(self):
        contract_function = self.__interface_agent.functions.withdrawPolicyReward()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def set_min_reward_rate(self, min_rate: int):
        contract_function = self.__interface_agent.functions.setMinRewardRate(min_rate)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=self.__beneficiary)
        return receipt

    def set_restaking(self, value: bool) -> dict:
        """
        Enable automatic restaking for a fixed duration of lock periods.
        If set to True, then all staking rewards will be automatically added to locked stake.
        """
        contract_function = self.__interface_agent.functions.setReStake(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=self.__beneficiary)
        # TODO: Handle ReStakeSet event (see #1193)
        return receipt

    def lock_restaking(self, release_period: int) -> dict:
        contract_function = self.__interface_agent.functions.lockReStake(release_period)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=self.__beneficiary)
        # TODO: Handle ReStakeLocked event (see #1193)
        return receipt

    def set_winding_down(self, value: bool) -> dict:
        """
                Enable wind down for stake.
                If set to True, then stakes duration will be decreasing in each period with `confirmActivity()`.
                """
        contract_function = self.__interface_agent.functions.setWindDown(value)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=self.__beneficiary)
        # TODO: Handle WindDownSet event (see #1193)
        return receipt


class AdjudicatorAgent(EthereumContractAgent):

    registry_contract_name = ADJUDICATOR_CONTRACT_NAME
    _proxy_name = DISPATCHER_CONTRACT_NAME

    @validate_checksum_address
    def evaluate_cfrag(self, evidence, sender_address: str):
        """
        Submits proof that a worker created wrong CFrag
        :param evidence:
        :param sender_address:
        :return:
        """
        payload = {'gas': 500_000}  # TODO #842: gas needed for use with geth.
        contract_function = self.contract.functions.evaluateCFrag(*evidence.evaluation_arguments())
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address,
                                                   payload=payload)
        return receipt

    def was_this_evidence_evaluated(self, evidence) -> bool:
        data_hash = sha256_digest(evidence.task.capsule, evidence.task.cfrag)
        return self.contract.functions.evaluatedCFrags(data_hash).call()

    @property
    def staking_escrow_contract(self) -> str:
        return self.contract.functions.escrow().call()

    @property
    def hash_algorithm(self) -> int:
        return self.contract.functions.hashAlgorithm().call()

    @property
    def base_penalty(self) -> int:
        return self.contract.functions.basePenalty().call()

    @property
    def penalty_history_coefficient(self) -> int:
        return self.contract.functions.penaltyHistoryCoefficient().call()

    @property
    def percentage_penalty_coefficient(self) -> int:
        return self.contract.functions.percentagePenaltyCoefficient().call()

    @property
    def reward_coefficient(self) -> int:
        return self.contract.functions.rewardCoefficient().call()

    @validate_checksum_address
    def penalty_history(self, staker_address: str) -> int:
        return self.contract.functions.penaltyHistory(staker_address).call()

    def slashing_parameters(self) -> Tuple:
        parameter_signatures = (
            'hashAlgorithm',                    # Hashing algorithm
            'basePenalty',                      # Base for the penalty calculation
            'penaltyHistoryCoefficient',        # Coefficient for calculating the penalty depending on the history
            'percentagePenaltyCoefficient',     # Coefficient for calculating the percentage penalty
            'rewardCoefficient',                # Coefficient for calculating the reward
        )

        def _call_function_by_name(name: str):
            return getattr(self.contract.functions, name)().call()

        staking_parameters = tuple(map(_call_function_by_name, parameter_signatures))
        return staking_parameters


class WorkLockAgent(EthereumContractAgent):

    registry_contract_name = "WorkLock"

    #
    # Transactions
    #

    @validate_checksum_address
    def bid(self, value: int, checksum_address: str) -> dict:
        """Bid for NU tokens with ETH."""
        contract_function = self.contract.functions.bid()
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=checksum_address,
                                                   payload={'value': value})
        return receipt

    @validate_checksum_address
    def cancel_bid(self, checksum_address: str) -> dict:
        """Cancel bid and refund deposited ETH."""
        contract_function = self.contract.functions.cancelBid()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=checksum_address)
        return receipt

    def force_refund(self, checksum_address: str, addresses: List[str]) -> dict:
        """Force refund to bidders who can get tokens more than maximum allowed."""
        addresses = sorted(addresses, key=str.casefold)
        contract_function = self.contract.functions.forceRefund(addresses)
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=checksum_address)
        return receipt

    @validate_checksum_address
    def verify_bidding_correctness(self,
                                   checksum_address: str,
                                   gas_limit: int,  # TODO - #842: Gas Management
                                   gas_to_save_state: int = 30000) -> dict:
        """Verify all bids are less than max allowed bid"""
        contract_function = self.contract.functions.verifyBiddingCorrectness(gas_to_save_state)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=checksum_address,
                                                   transaction_gas_limit=gas_limit)
        return receipt

    @validate_checksum_address
    def claim(self, checksum_address: str) -> dict:
        """
        Claim tokens - will be deposited and locked as stake in the StakingEscrow contract.
        """
        contract_function = self.contract.functions.claim()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=checksum_address)
        return receipt

    @validate_checksum_address
    def refund(self, checksum_address: str) -> dict:
        """Refund ETH for completed work."""
        contract_function = self.contract.functions.refund()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=checksum_address)
        return receipt

    @validate_checksum_address
    def withdraw_compensation(self, checksum_address: str) -> dict:
        """Withdraw compensation after force refund."""
        contract_function = self.contract.functions.withdrawCompensation()
        receipt = self.blockchain.send_transaction(contract_function=contract_function, sender_address=checksum_address)
        return receipt

    @validate_checksum_address
    def check_claim(self, checksum_address: str) -> bool:
        has_claimed = bool(self.contract.functions.workInfo(checksum_address).call()[2])
        return has_claimed
    
    #
    # Internal
    #

    @validate_checksum_address
    def get_refunded_work(self, checksum_address: str) -> int:
        work = self.contract.functions.workInfo(checksum_address).call()[1]
        return work

    #
    # Calls
    #

    @validate_checksum_address
    def get_available_refund(self, checksum_address: str) -> int:
        refund_eth = self.contract.functions.getAvailableRefund(checksum_address).call()
        return refund_eth

    @validate_checksum_address
    def get_available_compensation(self, checksum_address: str) -> int:
        compensation_eth = self.contract.functions.compensation(checksum_address).call()
        return compensation_eth

    @validate_checksum_address
    def get_deposited_eth(self, checksum_address: str) -> int:
        current_bid = self.contract.functions.workInfo(checksum_address).call()[0]
        return current_bid

    @property
    def lot_value(self) -> int:
        """
        Total number of tokens than can be bid for and awarded in or the number of NU
        tokens deposited before the bidding windows begins via tokenDeposit().
        """
        supply = self.contract.functions.tokenSupply().call()
        return supply

    def get_bonus_lot_value(self) -> int:
        """
        Total number of tokens than can be  awarded for bonus part of bid.
        """
        num_bidders = self.get_bidders_population()
        supply = self.lot_value - num_bidders * self.contract.functions.minAllowableLockedTokens().call()
        return supply

    @validate_checksum_address
    def get_remaining_work(self, checksum_address: str) -> int:
        """Get remaining work periods until full refund for the target address."""
        result = self.contract.functions.getRemainingWork(checksum_address).call()
        return result

    def get_bonus_eth_supply(self) -> int:
        supply = self.contract.functions.bonusETHSupply().call()
        return supply

    def get_eth_supply(self) -> int:
        num_bidders = self.get_bidders_population()
        min_bid = self.minimum_allowed_bid
        supply = num_bidders * min_bid + self.get_bonus_eth_supply()
        return supply

    def get_bonus_refund_rate(self) -> int:
        f = self.contract.functions
        slowing_refund = f.SLOWING_REFUND().call()
        boosting_refund = f.boostingRefund().call()
        refund_rate = self.get_bonus_deposit_rate() * slowing_refund / boosting_refund
        return refund_rate

    def get_bonus_deposit_rate(self) -> int:
        try:
            deposit_rate = self.get_bonus_lot_value() // self.get_bonus_eth_supply()
        except ZeroDivisionError:
            return 0
        return deposit_rate

    def eth_to_tokens(self, value: int) -> int:
        tokens = self.contract.functions.ethToTokens(value).call()
        return tokens

    def eth_to_work(self, value: int) -> int:
        tokens = self.contract.functions.ethToWork(value).call()
        return tokens

    def work_to_eth(self, value: int) -> int:
        tokens = self.contract.functions.workToETH(value).call()
        return tokens

    def get_bidders_population(self) -> int:
        """Returns the number of bidders on the blockchain"""
        return self.contract.functions.getBiddersLength().call()

    def get_bidders(self) -> List[str]:
        """Returns a list of bidders"""
        num_bidders = self.get_bidders_population()
        bidders = [self.contract.functions.bidders(i).call() for i in range(num_bidders)]
        return bidders

    def is_claiming_available(self) -> bool:
        """Returns True if claiming is available"""
        return self.contract.functions.isClaimingAvailable().call()

    @property
    def next_bidder_to_check(self) -> int:
        """Returns the index of the next bidder to check as part of the bids verification process"""
        return self.contract.functions.nextBidderToCheck().call()

    def bidders_checked(self) -> bool:
        """Returns True if bidders have been checked"""
        bidders_population = self.get_bidders_population()
        return self.next_bidder_to_check == bidders_population

    @property
    def minimum_allowed_bid(self) -> int:
        min_bid = self.contract.functions.minAllowedBid().call()
        return min_bid

    @property
    def start_bidding_date(self) -> int:
        date = self.contract.functions.startBidDate().call()
        return date

    @property
    def end_bidding_date(self) -> int:
        date = self.contract.functions.endBidDate().call()
        return date

    @property
    def end_cancellation_date(self) -> int:
        date = self.contract.functions.endCancellationDate().call()
        return date

    def worklock_parameters(self) -> Tuple:
        parameter_signatures = (
            'tokenSupply',
            'startBidDate',
            'endBidDate',
            'endCancellationDate',
            'boostingRefund',
            'stakingPeriods',
            'minAllowedBid',
        )

        def _call_function_by_name(name: str):
            return getattr(self.contract.functions, name)().call()

        parameters = tuple(map(_call_function_by_name, parameter_signatures))
        return parameters


class SeederAgent(EthereumContractAgent):

    registry_contract_name = SEEDER_CONTRACT_NAME

    def enroll(self, sender_address: str, seed_address: str, ip: str, port: int) -> dict:
        # TODO: Protection for over-enrollment
        contract_function = self.contract.functions.enroll(seed_address, ip, port)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address)
        return receipt

    def refresh(self, sender_address: str, ip: str, port: int) -> dict:
        contract_function = self.contract.functions.refresh(ip, port)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address)
        return receipt

    def get_entries(self) -> int:
        length = self.contract.functions.getSeedArrayLength().call()
        return length

    def dump(self) -> list:
        total = self.get_entries()
        entries = list()
        for index in range(total):
            ip = self.contract.functions.seedArray(index).call()
            entry = self.contract.functions.seeds(ip).call()
            entries.append(entry)
        return entries


class MultiSigAgent(EthereumContractAgent):

    registry_contract_name = MULTISIG_CONTRACT_NAME

    Vector = List[str]

    @property
    def nonce(self) -> int:
        nonce = self.contract.functions.nonce().call()
        return nonce

    def get_owner(self, index: int) -> str:
        owner = self.contract.functions.owners(index).call()
        return owner

    @property
    def owners(self) -> Tuple[str]:
        i = 0
        owners = list()
        array_is_within_bounds = True
        while array_is_within_bounds:
            try:
                owner = self.get_owner(i)
            except (TransactionFailed, ValueError):
                array_is_within_bounds = False
            else:
                owners.append(owner)
                i += 1
        return tuple(owners)

    @property
    def threshold(self) -> int:
        threshold = self.contract.functions.required().call()
        return threshold

    @validate_checksum_address
    def is_owner(self, checksum_address: str) -> bool:
        result = self.contract.functions.isOwner(checksum_address).call()
        return result

    def add_owner(self, new_owner_address: str, sender_address: str) -> dict:
        transaction_function = self.contract.functions.addOwner(new_owner_address)
        receipt = self.blockchain.send_transaction(contract_function=transaction_function,
                                                   sender_address=sender_address)
        return receipt

    @validate_checksum_address
    def remove_owner(self, checksum_address: str, sender_address: str):
        transaction_function = self.contract.functions.removeOwner(checksum_address)
        receipt = self.blockchain.send_transaction(contract_function=transaction_function,
                                                   sender_address=sender_address)
        return receipt

    def get_unsigned_transaction_hash(self,
                                      trustee_address: str,
                                      target_address: str,
                                      value: int,
                                      data: bytes,
                                      nonce: int
                                      ) -> bytes:
        transaction_args = (trustee_address,
                            target_address,
                            value,
                            data,
                            nonce)

        transaction_hash = self.contract.functions.getUnsignedTransactionHash(*transaction_args).call()
        return transaction_hash

    def execute(self,
                v: Vector,
                r: Vector,
                s: Vector,
                transaction_function,
                value: int,
                sender_address: str
                ) -> dict:
        contract_function = self.contract.functions.execute(v, r, s,
                                                            transaction_function.address,
                                                            value,
                                                            transaction_function.data)
        receipt = self.blockchain.send_transaction(contract_function=contract_function,
                                                   sender_address=sender_address)
        return receipt

