"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import random
from abc import ABC
from twisted.logger import Logger

from constant_sorrow.constants import NO_CONTRACT_AVAILABLE, NO_BENEFICIARY, CONTRACT_NOT_DEPLOYED
from typing import Generator, List, Tuple, Union
from web3.contract import Contract

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.registry import AllocationRegistry


class EthereumContractAgent(ABC):
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    registry_contract_name = NotImplemented
    _forward_address = True
    _proxy_name = None

    class ContractNotDeployed(Exception):
        pass

    def __init__(self, blockchain: Blockchain = None, contract: Contract = None) -> None:

        self.log = Logger(self.__class__.__name__)

        if blockchain is None:
            blockchain = Blockchain.connect()
        self.blockchain = blockchain

        if contract is None:  # Fetch the contract
            contract = self.blockchain.interface.get_contract_by_name(name=self.registry_contract_name,
                                                                      proxy_name=self._proxy_name,
                                                                      use_proxy_address=self._forward_address)
        self.__contract = contract
        super().__init__()
        self.log.info("Initialized new {} for {} with {} and {}".format(self.__class__.__name__,
                                                                        self.contract_address,
                                                                        self.blockchain.interface.provider_uri,
                                                                        self.blockchain.interface.registry.filepath))

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self.blockchain, self.registry_contract_name)

    def __eq__(self, other):
        return bool(self.contract_address == other.contract_address)

    @property
    def contract(self):
        return self.__contract

    @property
    def contract_address(self):
        return self.__contract.address

    @property
    def contract_name(self) -> str:
        return self.registry_contract_name


class NucypherTokenAgent(EthereumContractAgent):

    registry_contract_name = "NuCypherToken"

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()

    def approve_transfer(self, amount: int, target_address: str, sender_address: str) -> str:
        """Approve the transfer of token from the sender address to the target address."""

        txhash = self.contract.functions.approve(target_address, amount)\
            .transact({'from': sender_address})#, 'gas': 40000})  # TODO: needed for use with geth.

        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def transfer(self, amount: int, target_address: str, sender_address: str):
        """
        function transferFrom(address _from, address _to, uint256 _value) public returns (bool) {
        """
        self.approve_transfer(amount=amount, target_address=target_address, sender_address=sender_address)
        txhash = self.contract.functions.transfer(target_address, amount).transact({'from': sender_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash


class MinerAgent(EthereumContractAgent):

    registry_contract_name = "MinersEscrow"
    _proxy_name = "Dispatcher"

    class NotEnoughMiners(Exception):
        pass

    #
    # Miner Network Status
    #

    def get_miner_population(self) -> int:
        """Returns the number of miners on the blockchain"""
        return self.contract.functions.getMinersLength().call()

    def get_current_period(self) -> int:
        """Returns the current period"""
        return self.contract.functions.getCurrentPeriod().call()

    #
    # MinersEscrow Contract API
    #

    def get_locked_tokens(self, miner_address: str, periods: int = 0) -> int:
        """
        Returns the amount of tokens this miner has locked.

        TODO: Validate input (periods not less then 0)
        """
        return self.contract.functions.getLockedTokens(miner_address, periods).call()

    def owned_tokens(self, address: str) -> int:
        return self.contract.functions.minerInfo(address).call()[0]

    def get_stake_info(self, miner_address: str, stake_index: int):
        first_period, *others, locked_value = self.contract.functions.getStakeInfo(miner_address, stake_index).call()
        last_period = self.contract.functions.getLastPeriodOfStake(miner_address, stake_index).call()
        return first_period, last_period, locked_value

    def get_all_stakes(self, miner_address: str):
        stakes_length = self.contract.functions.getStakesLength(miner_address).call()
        for stake_index in range(stakes_length):
            yield self.get_stake_info(miner_address=miner_address, stake_index=stake_index)

    def deposit_tokens(self, amount: int, lock_periods: int, sender_address: str) -> str:
        """Send tokes to the escrow from the miner's address"""
        deposit_txhash = self.contract.functions.deposit(amount, lock_periods)\
            .transact({'from': sender_address, 'gas': 2000000})  # TODO: Causes tx to fail without high amount of gas
        self.blockchain.wait_for_receipt(deposit_txhash)
        return deposit_txhash

    def divide_stake(self, miner_address: str, stake_index: int, target_value: int, periods: int):
        tx = self.contract.functions.divideStake(stake_index,   # uint256 _index,
                                                 target_value,  # uint256 _newValue,
                                                 periods        # uint256 _periods
                                                 ).transact({'from': miner_address})
        self.blockchain.wait_for_receipt(tx)
        return tx

    def confirm_activity(self, node_address: str) -> str:
        """Miner rewarded for every confirmed period"""

        txhash = self.contract.functions.confirmActivity().transact({'from': node_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def mint(self, node_address) -> Tuple[str, str]:
        """
        Computes reward tokens for the miner's account;
        This is only used to calculate the reward for the final period of a stake,
        when you intend to withdraw 100% of tokens.
        """

        mint_txhash = self.contract.functions.mint().transact({'from': node_address})
        self.blockchain.wait_for_receipt(mint_txhash)
        return mint_txhash

    def collect_staking_reward(self, collector_address) -> str:
        """Withdraw tokens rewarded for staking."""

        token_amount = self.contract.functions.minerInfo(collector_address).call()[0]
        staked_amount = max(self.contract.functions.getLockedTokens(collector_address).call(),
                            self.contract.functions.getLockedTokens(collector_address, 1).call())

        collection_txhash = self.contract.functions.withdraw(token_amount - staked_amount).transact({'from': collector_address})

        self.blockchain.wait_for_receipt(collection_txhash)

        return collection_txhash

    #
    # Contract Utilities
    #
    def swarm(self) -> Union[Generator[str, None, None], Generator[str, None, None]]:
        """
        Returns an iterator of all miner addresses via cumulative sum, on-network.

        Miner addresses are returned in the order in which they registered with the MinersEscrow contract's ledger

        """

        for index in range(self.get_miner_population()):
            miner_address = self.contract.functions.miners(index).call()
            yield miner_address

    def sample(self, quantity: int, duration: int, additional_ursulas: float=1.7, attempts: int=5) -> List[str]:
        """
        Select n random staking Ursulas, according to their stake distribution.
        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.
        See full diagram here: https://github.com/nucypher/kms-whitepaper/blob/master/pdf/miners-ruler.pdf
        """

        miners_population = self.get_miner_population()
        if quantity > miners_population:
            raise self.NotEnoughMiners('{} miners are available'.format(miners_population))

        system_random = random.SystemRandom()
        n_select = round(quantity*additional_ursulas)            # Select more Ursulas
        n_tokens = self.contract.functions.getAllLockedTokens(duration).call()

        if n_tokens == 0:
            raise self.NotEnoughMiners('There are no locked tokens for duration {}.'.format(duration))

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))

            deltas = []
            for next_point, previous_point in zip(points[1:], points[:-1]):
                deltas.append(next_point - previous_point)

            addresses = set(self.contract.functions.sample(deltas, duration).call())
            addresses.discard(str(constants.NULL_ADDRESS))

            if len(addresses) >= quantity:
                return system_random.sample(addresses, quantity)

        raise self.NotEnoughMiners('Selection failed after {} attempts'.format(attempts))


class PolicyAgent(EthereumContractAgent):

    registry_contract_name = "PolicyManager"
    _proxy_name = "Dispatcher"

    def create_policy(self,
                      policy_id: str,
                      author_address: str,
                      value: int,
                      periods: int,
                      initial_reward: int,
                      node_addresses: List[str]) -> str:

        txhash = self.contract.functions.createPolicy(policy_id,
                                                      periods,
                                                      initial_reward,
                                                      node_addresses).transact({'from': author_address,
                                                                                'value': value})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def fetch_policy(self, policy_id: str) -> list:
        """Fetch raw stored blockchain data regarding the policy with the given policy ID"""
        blockchain_record = self.contract.functions.policies(policy_id).call()
        return blockchain_record

    def revoke_policy(self, policy_id: bytes, author_address) -> str:
        """Revoke by arrangement ID; Only the policy's author_address can revoke the policy."""
        txhash = self.contract.functions.revokePolicy(policy_id).transact({'from': author_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def collect_policy_reward(self, collector_address: str):
        """Collect rewarded ETH"""
        policy_reward_txhash = self.contract.functions.withdraw().transact({'from': collector_address})
        self.blockchain.wait_for_receipt(policy_reward_txhash)
        return policy_reward_txhash

    def fetch_policy_arrangements(self, policy_id):
        record_count = self.contract.functions.getArrangementsLength(policy_id).call()
        for index in range(record_count):
            arrangement = self.contract.functions.getArrangementInfo(policy_id, index).call()
            yield arrangement

    def revoke_arrangement(self, policy_id: str, node_address: str, author_address: str):
        txhash = self.contract.functions.revokeArrangement(policy_id, node_address).transact({'from': author_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def calculate_refund(self, policy_id: str, author_address: str) -> str:
        txhash = self.contract.functions.calculateRefundValue(policy_id).transact({'from': author_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def collect_refund(self, policy_id: str, author_address: str) -> str:
        txhash = self.contract.functions.refund(policy_id).transact({'from': author_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash


class UserEscrowAgent(EthereumContractAgent):

    registry_contract_name = "UserEscrow"
    _proxy_name = NotImplemented
    _forward_address = False
    __allocation_registry = AllocationRegistry

    class UserEscrowProxyAgent(EthereumContractAgent):
        registry_contract_name = "UserEscrowProxy"
        _proxy_name = "UserEscrowLibraryLinker"
        _forward_address = False

        def _generate_beneficiary_agency(self, principal_address: str):
            contract = self.blockchain.interface.w3.eth.contract(address=principal_address, abi=self.contract.abi)
            return contract

    def __init__(self,
                 beneficiary: str,
                 blockchain: Blockchain = None,
                 allocation_registry: AllocationRegistry = None,
                 *args, **kwargs) -> None:

        self.blockchain = blockchain or Blockchain.connect()

        self.__allocation_registry = allocation_registry or self.__allocation_registry()
        self.__beneficiary = beneficiary
        self.__principal_contract = NO_CONTRACT_AVAILABLE
        self.__proxy_contract = NO_CONTRACT_AVAILABLE

        # Sets the above
        self.__read_principal()
        self.__read_proxy()
        super().__init__(blockchain=self.blockchain, contract=self.principal_contract, *args, **kwargs)

    def __read_proxy(self):
        self.__proxy_agent = self.UserEscrowProxyAgent(blockchain=self.blockchain)
        contract = self.__proxy_agent._generate_beneficiary_agency(principal_address=self.principal_contract.address)
        self.__proxy_contract = contract

    def __fetch_principal_contract(self, contract_address: str = None) -> None:
        """Fetch the UserEscrow deployment directly from the AllocationRegistry."""
        if contract_address is not None:
            contract_data = self.__allocation_registry.search(contract_address=contract_address)
        else:
            contract_data = self.__allocation_registry.search(beneficiary_address=self.beneficiary)
        address, abi = contract_data
        principal_contract = self.blockchain.interface.w3.eth.contract(abi=abi,
                                                                       address=address,
                                                                       ContractFactoryClass=Contract)
        self.__principal_contract = principal_contract

    def __set_owner(self) -> None:
        owner = self.owner
        self.__beneficiary = owner

    def __read_principal(self, contract_address: str = None) -> None:
        self.__fetch_principal_contract(contract_address=contract_address)
        self.__set_owner()

    @property
    def owner(self):
        owner = self.principal_contract.functions.owner().call()
        return owner

    @property
    def beneficiary(self):
        return self.__beneficiary

    @property
    def proxy_contract(self):
        if self.__proxy_contract is NO_CONTRACT_AVAILABLE:
            raise RuntimeError("{} not available".format(self.registry_contract_name))
        return self.__proxy_contract

    @property
    def principal_contract(self):
        """Directly reference the beneficiary's deployed contract instead of the proxy contracts's interface"""
        if self.__principal_contract is NO_CONTRACT_AVAILABLE:
            raise RuntimeError("{} not available".format(self.registry_contract_name))
        return self.__principal_contract

    @property
    def unvested_tokens(self) -> int:
        return self.principal_contract.functions.getLockedTokens().call()

    @property
    def end_timestamp(self) -> int:
        return self.principal_contract.functions.endLockTimestamp().call()

    def lock(self, amount: int, periods: int) -> str:
        txhash = self.__proxy_contract.functions.lock(amount, periods).transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def withdraw_tokens(self, value: int) -> str:
        txhash = self.principal_contract.functions.withdrawTokens(value).transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def withdraw_eth(self) -> str:
        txhash = self.principal_contract.functions.withdrawETH().transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def deposit_as_miner(self, value: int, periods: int) -> str:
        txhash = self.__proxy_contract.functions.depositAsMiner(value, periods).transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def withdraw_as_miner(self, value: int) -> str:
        txhash = self.__proxy_contract.functions.withdrawAsMiner(value).transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def confirm_activity(self) -> str:
        txhash = self.__proxy_contract.functions.confirmActivity().transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def mint(self) -> str:
        txhash = self.__proxy_contract.functions.mint().transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def collect_policy_reward(self) -> str:
        txhash = self.__proxy_contract.functions.withdrawPolicyReward().transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def set_min_reward_rate(self, rate: int) -> str:
        txhash = self.__proxy_contract.functions.setMinRewardRate(rate).transact({'from': self.__beneficiary})
        self.blockchain.wait_for_receipt(txhash)
        return txhash
