import random
from abc import ABC
from enum import Enum
from typing import Generator, List, Tuple, Union

from constant_sorrow import constants
from web3.contract import Contract

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain


class EthereumContractAgent(ABC):
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    _principal_contract_name = NotImplemented
    __contract_address = NotImplemented

    class ContractNotDeployed(Exception):
        pass

    def __init__(self, blockchain: Blockchain=None, contract: Contract=None, *args, **kwargs):

        if blockchain is None:
            blockchain = Blockchain.connect()
        self.blockchain = blockchain

        if contract is None:
            address = blockchain.interface.get_contract_address(contract_name=self._principal_contract_name)[-1]  # TODO: Handle multiple
            contract = blockchain.interface.get_contract(address)
        self.__contract = contract

        super().__init__(*args, **kwargs)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self.blockchain, self._principal_contract_name)

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
        return self._principal_contract_name

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()


class NucypherTokenAgent(EthereumContractAgent):
    _principal_contract_name = "NuCypherToken"

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

    _principal_contract_name = "MinersEscrow"

    class NotEnoughMiners(Exception):
        pass

    class MinerInfo(Enum):
        VALUE = 0
        DECIMALS = 1
        LAST_ACTIVE_PERIOD = 2
        CONFIRMED_PERIOD_1 = 3
        CONFIRMED_PERIOD_2 = 4

    def __init__(self, token_agent: NucypherTokenAgent=None, *args, **kwargs):
        token_agent = token_agent if token_agent is not None else NucypherTokenAgent()
        super().__init__(blockchain=token_agent.blockchain, *args, **kwargs)
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

    def get_total_locked_tokens(self) -> int:
        """Returns the total amount of locked tokens on the blockchain."""
        return self.contract.functions.getAllLockedTokens().call()

    #
    # MinersEscrow Contract API
    #

    def get_locked_tokens(self, node_address):
        """Returns the amount of tokens this miner has locked."""
        return self.contract.functions.getLockedTokens(node_address).call()

    def get_stake_info(self, miner_address: str, stake_index: int):
        stake_info = self.contract.functions.getStakeInfo(miner_address, stake_index).call()
        return stake_info

    def deposit_tokens(self, amount: int, lock_periods: int, sender_address: str) -> str:
        """Send tokes to the escrow from the miner's address"""

        deposit_txhash = self.contract.functions.deposit(amount, lock_periods).transact({'from': sender_address})
        self.blockchain.wait_for_receipt(deposit_txhash)
        return deposit_txhash

    def divide_stake(self, miner_address, balance, end_period, target_value, periods):
        tx = self.contract.functions.divideStake(balance,       # uint256 _oldValue
                                                 end_period,    # uint256 _lastPeriod,
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
        """Computes and transfers tokens to the miner's account"""

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

    # Node Datastore #

    def _publish_datastore(self, node_address: str, data) -> str:
        """Publish new data to the MinerEscrow contract as a public record associated with this miner."""

        txhash = self.contract.functions.setMinerId(data).transact({'from': node_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def _get_datastore_entries(self, node_address: str) -> int:
        count_bytes = self.contract.functions.getMinerIdsLength(node_address).call()
        datastore_entries = self.blockchain.interface.w3.toInt(count_bytes)
        return datastore_entries

    def _fetch_node_datastore(self, node_address):
        """Cache a generator of all asosciated contract data for this miner."""

        datastore_entries = self._get_datastore_entries(node_address=node_address)

        def __node_datastore_reader():
            for index in range(datastore_entries):
                value = self.contract.functions.getMinerId(node_address, index).call()
                yield value

        return __node_datastore_reader()


    #
    # Contract Utilities
    #
    def swarm(self, fetch_data: bool=False) -> Union[Generator[str, None, None], Generator[Tuple[str, bytes], None, None]]:
        """
        Returns an iterator of all miner addresses via cumulative sum, on-network.
        if fetch_data is true, tuples containing the address and the miners stored data are yielded.

        Miner addresses are returned in the order in which they registered with the MinersEscrow contract's ledger

        """

        for index in range(self.get_miner_population()):

            miner_address = self.contract.functions.miners(index).call()
            validated_address = self.blockchain.interface.w3.toChecksumAddress(miner_address)  # string address of next node

            if fetch_data is True:
                stored_miner_data = self.contract.functions.getMinerIdsLength(miner_address).call()
                yield (validated_address, stored_miner_data)
            else:
                yield validated_address

    def sample(self, quantity: int, additional_ursulas: float=1.7, attempts: int=5, duration: int=10) -> List[str]:
        """
        Select n random staking Ursulas, according to their stake distribution.
        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.

                _startIndex
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stopIndex
                |
                |       _delta
                |---------------------------->|
                |
                |                       shift
                |                      |----->|


        See full diagram here: https://github.com/nucypher/kms-whitepaper/blob/master/pdf/miners-ruler.pdf

        """

        system_random = random.SystemRandom()
        n_select = round(quantity*additional_ursulas)            # Select more Ursulas
        n_tokens = self.get_total_locked_tokens()

        if not n_tokens > 0:
            raise self.NotEnoughMiners('There are no locked tokens.')

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))
            deltas = [i-j for i, j in zip(points[1:], points[:-1])]

            addrs, addr, index, shift = set(), str(constants.NULL_ADDRESS), 0, 0
            for delta in deltas:
                addr, index, shift = self.contract.functions.findCumSum(index, delta + shift, duration).call()
                addrs.add(addr)

            if len(addrs) >= quantity:
                return system_random.sample(addrs, quantity)

        raise self.NotEnoughMiners('Selection failed after {} attempts'.format(attempts))


class PolicyAgent(EthereumContractAgent):

    _principal_contract_name = "PolicyManager"

    def __init__(self, miner_agent: MinerAgent, *args, **kwargs):
        super().__init__(blockchain=miner_agent.blockchain, *args, **kwargs)
        self.miner_agent = miner_agent
        self.token_agent = miner_agent.token_agent

    def fetch_arrangement_data(self, arrangement_id: bytes) -> list:
        blockchain_record = self.contract.functions.policies(arrangement_id).call()
        return blockchain_record

    def revoke_arrangement(self, arrangement_id: bytes, author):
        """
        Revoke by arrangement ID; Only the policy author can revoke the policy
        """

        txhash = self.contract.functions.revokePolicy(arrangement_id).transact({'from': author.address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash
