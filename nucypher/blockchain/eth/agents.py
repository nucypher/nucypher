import random
from abc import ABC
from typing import Generator, List, Tuple, Union

from constant_sorrow import constants

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


class EthereumContractAgent(ABC):
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    _upgradeable = NotImplemented

    principal_contract_name = NotImplemented
    __contract_address = NotImplemented
    __instance = None

    class ContractNotDeployed(Exception):
        pass

    def __new__(cls, *args, **kwargs) -> 'EthereumContractAgent':
        if cls.__instance is None:
            cls.__instance = super(EthereumContractAgent, cls).__new__(cls)
        return cls.__instance

    def __init__(self,
                 blockchain: Blockchain = None,
                 registry_filepath: str = None,
                 *args, **kwargs) -> None:

        if blockchain is None:
            blockchain = Blockchain.connect()
        self.blockchain = blockchain

        if registry_filepath is not None:
            # TODO: Warn on override?
            self.blockchain.interface._registry._swap_registry(filepath=registry_filepath)

        # Fetch the contract by reading address and abi from the registry and blockchain
        contract = self.blockchain.interface.get_contract_by_name(name=self.principal_contract_name,
                                                                  upgradeable=self._upgradeable)

        self.__contract = contract
        super().__init__()

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self.blockchain, self.principal_contract_name)

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
        return self.principal_contract_name

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()


class NucypherTokenAgent(EthereumContractAgent):
    principal_contract_name = "NuCypherToken"
    _upgradeable = False
    __instance = None

    def approve_transfer(self, amount: int, target_address: str, sender_address: str) -> str:
        """Approve the transfer of token from the sender address to the target address."""

        txhash = self.contract.functions.approve(target_address, amount).transact({'from': sender_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash


class MinerAgent(EthereumContractAgent):
    """
    Wraps NuCypher's Escrow solidity smart contract

    In order to become a participant of the network,
    a miner locks tokens by depositing to the Escrow contract address
    for a duration measured in periods.
    """

    principal_contract_name = "MinersEscrow"
    _upgradeable = True
    __instance = None  # TODO: constants.NO_CONTRACT_AVAILABLE

    class NotEnoughMiners(Exception):
        pass

    def __init__(self,
                 token_agent: NucypherTokenAgent = None,
                 registry_filepath: str = None,
                 *args, **kwargs
                 ) -> None:

        token_agent = token_agent if token_agent is not None else NucypherTokenAgent(registry_filepath=registry_filepath)

        super().__init__(blockchain=token_agent.blockchain,
                         registry_filepath=registry_filepath,
                         *args, **kwargs)

        self.token_agent = token_agent

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

    def get_locked_tokens(self, node_address):
        """Returns the amount of tokens this miner has locked."""
        return self.contract.functions.getLockedTokens(node_address).call()

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

        deposit_txhash = self.contract.functions.deposit(amount, lock_periods).transact({'from': sender_address, 'gas': 2000000})  # TODO: what..?
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
        """Computes reward tokens for the miner's account"""

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

    principal_contract_name = "PolicyManager"
    _upgradeable = True
    __instance = None

    def __init__(self,
                 miner_agent: MinerAgent = None,
                 registry_filepath=None,
                 *args, **kwargs) -> None:
        miner_agent = miner_agent if miner_agent is not None else MinerAgent(registry_filepath=registry_filepath)
        super().__init__(blockchain=miner_agent.blockchain, registry_filepath=registry_filepath, *args, **kwargs)
        self.miner_agent = miner_agent
        self.token_agent = miner_agent.token_agent

    def create_policy(self, policy_id: str, author_address: str, value: int,
                      periods: int, reward: int, node_addresses: List[str]):

        txhash = self.contract.functions.createPolicy(policy_id,
                                                      periods,
                                                      reward,
                                                      node_addresses).transact({'from': author_address,
                                                                                'value': value})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def fetch_policy(self, policy_id: str) -> list:
        """Fetch raw stored blockchain data regarding the policy with the given policy ID"""
        blockchain_record = self.contract.functions.policies(policy_id).call()
        return blockchain_record

    def revoke_policy(self, policy_id: bytes, author) -> str:
        """
        Revoke by arrangement ID; Only the policy's author can revoke the policy.

        :param policy_id: An existing arrangementID to revoke on the blockchain.

        """

        txhash = self.contract.functions.revokePolicy(policy_id).transact({'from': author.address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def collect_policy_reward(self, collector_address: str):
        """Collect rewarded ETH"""
        policy_reward_txhash = self.contract.functions.withdraw().transact({'from': collector_address})
        self.blockchain.wait_for_receipt(policy_reward_txhash)
        return policy_reward_txhash

    def fetch_policy_arrangements(self, policy_id):
        records = self.contract.functions.getArrangementsLength(policy_id).call()
        for records in range(records):
            arrangement = self.contract.functions.getArrangementInfo(policy_id, 0).call()[records]
            yield arrangement

    def revoke_arrangement(self, policy_id: str, node_address: str):
        txhash = self.contract.functions.revokeArrangement(policy_id, node_address)
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

    principal_contract_name = "UserEscrow"
    _upgradeable = True
    __instance = None
