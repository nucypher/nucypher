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
import functools
import pprint
import random
from typing import Generator, List, Tuple, Union, Callable

import eth_tester
import web3
from constant_sorrow.constants import NO_CONTRACT_AVAILABLE, UNKNOWN_TX_STATUS
from eth_tester.exceptions import TransactionFailed
from web3.exceptions import ValidationError, TimeExhausted
from eth_utils.address import to_checksum_address, is_checksum_address
from twisted.logger import Logger
from web3.contract import Contract

from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.registry import AllocationRegistry


class Agency(type):
    __agents = dict()

    def __call__(cls, *args, **kwargs):
        if cls not in cls.__agents:
            cls.__agents[cls] = super().__call__(*args, **kwargs)
        return cls.__agents[cls]

    @classmethod
    def clear(mcs):
        mcs.__agents = dict()

    @property
    def agents(cls):
        return cls.__agents


def __transact(broadcaster: Callable,
               data: Union[dict, bytes],
               blockchain: Blockchain) -> dict:

    try:
        txhash = broadcaster(data)  # <--- Transmit the transaction (signed or presigned)
    except eth_tester.exceptions.TransactionFailed:
        raise
    except web3.exceptions.ValidationError:
        raise

    try:
        # TODO: Use web3 abstractions for transaction receipts
        # TODO: Implement timeout from interfaces or agency
        receipt = blockchain.interface.client.w3.eth.waitForTransactionReceipt(txhash, timeout=180)
    except web3.exceptions.TimeExhausted:
        raise

    # Primary check
    status = receipt.get('status', UNKNOWN_TX_STATUS)
    if status is 0:
        pretty_receipt = pprint.pformat(receipt, indent=2)
        failure = f"Transaction returned status code 0. Full receipt: \n {pretty_receipt}"
        raise TransactionFailed(failure)

    # Secondary check
    if status is UNKNOWN_TX_STATUS:
        pretty_receipt = pprint.pformat(receipt, indent=2)
        if receipt["gas"] == receipt["gasUsed"]:
            raise TransactionFailed(f"Transaction consumed 100% of transaction gas. Full receipt: \n {pretty_receipt}")

    return receipt


def transaction(agent_func, confirmations: int = 1, device=None) -> Callable:

    @functools.wraps(agent_func)
    def wrapped(agent, *args, **kwargs) -> dict:

        # Produce the transaction builder
        try:
            transaction_builder, payload = agent_func(agent, *args, **kwargs)
        except web3.exceptions.ValidationError:
            raise

        # Validate sender
        sender_address = payload['from']
        if not is_checksum_address(sender_address):
            raise ValidationError(f"{sender_address} is not a valid EIP-55 checksum address.")

        # Gas Control
        function_name = transaction_builder.abi['name']
        transaction_gas_limits = agent.DEFAULT_TRANSACTION_GAS
        gas = transaction_gas_limits.get(function_name)
        if not gas:
            gas = transaction_builder.estimateGas(payload)
        payload['gas'] = gas

        # HW Wallet Transaction Signer
        if device:
            unsigned_transaction = transaction_builder.buildTransaction(payload)
            signed_transaction = device.sign_transaction(unsigned_transaction)
            if not device.broadcast_now:
                raise NotImplementedError
            transaction_broadcaster = agent.blockchain.interface.client.w3.sendRawTransaction
            payload = signed_transaction

        # We3 Transaction Signer
        else:
            transaction_broadcaster = transaction_builder.transact

        # Broadcast
        receipt = __transact(broadcaster=transaction_broadcaster,
                             data=payload,
                             blockchain=agent.blockchain)

        # Post-Broadcast
        txhash = receipt['transactionHash'].hex()
        agent.log.debug(f'[TX-{agent.contract_name.upper()}-{function_name.upper()}] {txhash}')

        if confirmations:
            # TODO: Handle transaction confirmations?
            pass

        return receipt
    return wrapped


class EthereumContractAgent:
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    registry_contract_name = NotImplemented
    _forward_address = True
    _proxy_name = None

    DEFAULT_TRANSACTION_GAS = {}

    class ContractNotDeployed(Exception):
        pass

    def __init__(self,
                 blockchain: Blockchain = None,
                 contract: Contract = None,
                 transaction_gas: int = None
                 ) -> None:

        self.log = Logger(self.__class__.__name__)

        if blockchain is None:
            blockchain = Blockchain.connect()
        self.blockchain = blockchain

        if contract is None:  # Fetch the contract
            contract = self.blockchain.interface.get_contract_by_name(name=self.registry_contract_name,
                                                                      proxy_name=self._proxy_name,
                                                                      use_proxy_address=self._forward_address)
        self.__contract = contract

        if not transaction_gas:
            transaction_gas = EthereumContractAgent.DEFAULT_TRANSACTION_GAS
        self.transaction_gas = transaction_gas

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


class NucypherTokenAgent(EthereumContractAgent, metaclass=Agency):

    registry_contract_name = "NuCypherToken"

    def get_balance(self, address: str = None) -> int:
        """Get the balance of a token address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()

    @transaction
    def approve_transfer(self, amount: int, target_address: str, sender_address: str):
        """Approve the transfer of token from the sender address to the target address."""
        payload = {'from': sender_address, 'gas': 500_000}  # TODO #413: gas needed for use with geth.
        transaction_builder = self.contract.functions.approve(target_address, amount)
        return transaction_builder, payload

    @transaction
    def transfer(self, amount: int, target_address: str, sender_address: str):
        _approve_txhash = self.approve_transfer(amount=amount, target_address=target_address, sender_address=sender_address)
        payload = {'from': sender_address}
        transaction_builder = self.contract.functions.transfer(target_address, amount)
        return transaction_builder, payload


class StakingEscrowAgent(EthereumContractAgent, metaclass=Agency):

    registry_contract_name = "StakingEscrow"
    _proxy_name = "Dispatcher"

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

    #
    # StakingEscrow Contract API
    #

    def get_locked_tokens(self, staker_address: str, periods: int = 0) -> int:
        """
        Returns the amount of tokens this staker has locked
        for a given duration in periods measured from the current period forwards.
        """
        if periods < 0:
            raise ValueError(f"Periods value must not be negative, Got '{periods}'.")
        return self.contract.functions.getLockedTokens(staker_address, periods).call()

    def owned_tokens(self, address: str) -> int:
        return self.contract.functions.stakerInfo(address).call()[0]

    def get_substake_info(self, staker_address: str, stake_index: int) -> Tuple[int, int, int]:
        first_period, *others, locked_value = self.contract.functions.getSubStakeInfo(staker_address, stake_index).call()
        last_period = self.contract.functions.getLastPeriodOfSubStake(staker_address, stake_index).call()
        return first_period, last_period, locked_value

    def get_raw_substake_info(self, staker_address: str, stake_index: int) -> Tuple[int, int, int, int]:
        result = self.contract.functions.getSubStakeInfo(staker_address, stake_index).call()
        first_period, last_period, periods, locked = result
        return first_period, last_period, periods, locked

    def get_all_stakes(self, staker_address: str):
        stakes_length = self.contract.functions.getSubStakesLength(staker_address).call()
        if stakes_length == 0:
            return iter(())  # Empty iterable, There are no stakes
        for stake_index in range(stakes_length):
            yield self.get_substake_info(staker_address=staker_address, stake_index=stake_index)

    @transaction
    def deposit_tokens(self, amount: int, lock_periods: int, sender_address: str):
        """Send tokens to the escrow from the staker's address"""
        payload = {'from': sender_address}
        transaction_builder = self.contract.functions.deposit(amount, lock_periods)
        return transaction_builder, payload

    @transaction
    def divide_stake(self, staker_address: str, stake_index: int, target_value: int, periods: int):
        payload = {'from': staker_address}
        transaction_builder = self.contract.functions.divideStake(stake_index, target_value, periods)
        return transaction_builder, payload

    def get_last_active_period(self, address: str) -> int:
        period = self.contract.functions.getLastActivePeriod(address).call()
        return int(period)

    def get_worker_from_staker(self, staker_address: str) -> str:
        worker = self.contract.functions.getWorkerFromStaker(staker_address).call()
        return to_checksum_address(worker)

    def get_staker_from_worker(self, worker_address: str) -> str:
        staker = self.contract.functions.getStakerFromWorker(worker_address).call()
        return to_checksum_address(staker)

    @transaction
    def set_worker(self, staker_address: str, worker_address: str):
        payload = {'from': staker_address}
        transaction_builder = self.contract.functions.setWorker(worker_address)
        return transaction_builder, payload

    def release_worker(self, staker_address: str):
        return self.set_worker(staker_address=staker_address, worker_address=Blockchain.NULL_ADDRESS)

    @transaction
    def confirm_activity(self, worker_address: str):
        """
        For each period that the worker confirms activity, the staker is rewarded.
        """
        payload = {'from': worker_address}
        transaction_builder = self.contract.functions.confirmActivity()
        return transaction_builder, payload

    @transaction
    def mint(self, staker_address: str):
        """
        Computes reward tokens for the staker's account;
        This is only used to calculate the reward for the final period of a stake,
        when you intend to withdraw 100% of tokens.
        """
        payload = {'from': staker_address}
        transaction_builder = self.contract.functions.mint()
        return transaction_builder, payload

    @validate_checksum_address
    def calculate_staking_reward(self, staker_address: str) -> int:
        token_amount = self.owned_tokens(staker_address)
        staked_amount = max(self.contract.functions.getLockedTokens(staker_address).call(),
                            self.contract.functions.getLockedTokens(staker_address, 1).call())
        reward_amount = token_amount - staked_amount
        return reward_amount

    @validate_checksum_address
    def collect_staking_reward(self, staker_address: str):
        """Withdraw tokens rewarded for staking."""
        reward_amount = self.calculate_staking_reward(staker_address=staker_address)
        return self.withdraw(staker_address=staker_address, amount=reward_amount)

    @transaction
    @validate_checksum_address
    def withdraw(self, staker_address: str, amount: int):
        """Withdraw tokens"""
        payload = {'from': staker_address, 'gas': 500_000}  # TODO: #842 Gas Management
        transaction_builder = self.contract.functions.withdraw(amount)
        return transaction_builder, payload

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

    def sample(self, quantity: int, duration: int, additional_ursulas: float = 1.7, attempts: int = 5) -> List[str]:
        """
        Select n random Stakers, according to their stake distribution.
        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.
        See full diagram here: https://github.com/nucypher/kms-whitepaper/blob/master/pdf/miners-ruler.pdf
        """

        stakers_population = self.get_staker_population()
        if quantity > stakers_population:
            raise self.NotEnoughStakers(f'There are {stakers_population} published stakers, need a total of {quantity}.')

        system_random = random.SystemRandom()
        n_select = round(quantity*additional_ursulas)            # Select more Ursulas
        n_tokens = self.contract.functions.getAllLockedTokens(duration).call()

        if n_tokens == 0:
            raise self.NotEnoughStakers('There are no locked tokens for duration {}.'.format(duration))

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))

            deltas = []
            for next_point, previous_point in zip(points[1:], points[:-1]):
                deltas.append(next_point - previous_point)

            addresses = set(self.contract.functions.sample(deltas, duration).call())
            addresses.discard(str(Blockchain.NULL_ADDRESS))

            if len(addresses) >= quantity:
                return system_random.sample(addresses, quantity)

        raise self.NotEnoughStakers('Selection failed after {} attempts'.format(attempts))


class PolicyAgent(EthereumContractAgent, metaclass=Agency):

    registry_contract_name = "PolicyManager"
    _proxy_name = "Dispatcher"

    @transaction
    def create_policy(self,
                      policy_id: str,
                      author_address: str,
                      value: int,
                      periods: int,
                      initial_reward: int,
                      node_addresses: List[str]):
        payload = {'from': author_address, 'value': value}
        transaction_builder = self.contract.functions.createPolicy(policy_id, periods, initial_reward, node_addresses)
        return transaction_builder, payload

    def fetch_policy(self, policy_id: str) -> list:
        """Fetch raw stored blockchain data regarding the policy with the given policy ID"""
        blockchain_record = self.contract.functions.policies(policy_id).call()
        return blockchain_record

    @transaction
    def revoke_policy(self, policy_id: bytes, author_address: str):
        """Revoke by arrangement ID; Only the policy's author_address can revoke the policy."""
        payload = {'from': author_address}
        transaction_builder = self.contract.functions.revokePolicy(policy_id)
        return transaction_builder, payload

    @transaction
    def collect_policy_reward(self, collector_address: str, staker_address: str):
        """Collect rewarded ETH"""
        payload = {'from': staker_address}  # TODO - #842
        transaction_builder = self.contract.functions.withdraw(collector_address)
        return transaction_builder, payload

    def fetch_policy_arrangements(self, policy_id):
        record_count = self.contract.functions.getArrangementsLength(policy_id).call()
        for index in range(record_count):
            arrangement = self.contract.functions.getArrangementInfo(policy_id, index).call()
            yield arrangement

    @transaction
    def revoke_arrangement(self, policy_id: str, node_address: str, author_address: str):
        payload = {'from': author_address}
        transaction_builder = self.contract.functions.revokeArrangement(policy_id, node_address)
        return transaction_builder, payload

    @transaction
    def calculate_refund(self, policy_id: str, author_address: str):
        payload = {'from': author_address}
        transaction_builder = self.contract.functions.calculateRefundValue(policy_id)
        return transaction_builder, payload

    @transaction
    def collect_refund(self, policy_id: str, author_address: str):
        payload = {'from': author_address}
        transaction_builder = self.contract.functions.refund(policy_id)
        return transaction_builder, payload


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
    def owner(self) -> str:
        owner = self.principal_contract.functions.owner().call()
        return owner

    @property
    def beneficiary(self) -> str:
        return self.__beneficiary

    @property
    def proxy_contract(self) -> Contract:
        if self.__proxy_contract is NO_CONTRACT_AVAILABLE:
            raise RuntimeError("{} not available".format(self.registry_contract_name))
        return self.__proxy_contract

    @property
    def principal_contract(self) -> Contract:
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

    @transaction
    def lock(self, amount: int, periods: int):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.lock(amount, periods)
        return transaction_builder, payload

    @transaction
    def withdraw_tokens(self, value: int):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.principal_contract.functions.withdrawTokens(value)
        return transaction_builder, payload

    @transaction
    def withdraw_eth(self):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.principal_contract.functions.withdrawETH()
        return transaction_builder, payload

    @transaction
    def deposit_as_staker(self, value: int, periods: int):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.depositAsStaker(value, periods)
        return transaction_builder, payload

    @transaction
    def withdraw_as_staker(self, value: int):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.withdrawAsStaker(value)
        return transaction_builder, payload

    @transaction
    def set_worker(self, worker_address: str):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.setWorker(worker_address)
        return transaction_builder, payload

    @transaction
    def mint(self):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.mint()
        return transaction_builder, payload

    @transaction
    def collect_policy_reward(self):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.withdrawPolicyReward()
        return transaction_builder, payload

    @transaction
    def set_min_reward_rate(self, rate: int):
        payload = {'from': self.__beneficiary}
        transaction_builder = self.__proxy_contract.functions.setMinRewardRate(rate)
        return transaction_builder, payload


class AdjudicatorAgent(EthereumContractAgent, metaclass=Agency):
    """TODO Issue #931"""

    registry_contract_name = "Adjudicator"
    _proxy_name = "Dispatcher"

    @transaction
    def evaluate_cfrag(self,
                       capsule_bytes: bytes,
                       capsule_signature_by_requester: bytes,
                       capsule_signature_by_requester_and_staker: bytes,
                       cfrag_bytes: bytes,
                       cfrag_signature_by_staker: bytes,
                       requester_public_key: bytes,
                       staker_public_key: bytes,
                       staker_public_key_signature: bytes,
                       precomputed_data: bytes):
        """

        From Contract Source:

        function evaluateCFrag(
            bytes memory _capsuleBytes,
            bytes memory _capsuleSignatureByRequester,
            bytes memory _capsuleSignatureByRequesterAndStaker,
            bytes memory _cFragBytes,
            bytes memory _cFragSignatureByStaker,
            bytes memory _requesterPublicKey,
            bytes memory _stakerPublicKey,
            bytes memory _stakerPublicKeySignature,
            bytes memory _preComputedData
        )

        :param capsule:
        :param capsule_signature_by_requester:
        :param capsule_signature_by_requester_and_staker:
        :param cfrag:
        :param cfrag_signature_by_staker:
        :param requester_public_key:
        :param staker_public_key:
        :param staker_piblc_key_signature:
        :param precomputed_data:
        :return:
        """
        # TODO: #931 - Challenge Agent and Actor - "Investigator"
