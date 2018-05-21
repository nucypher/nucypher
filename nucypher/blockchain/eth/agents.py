import random
from abc import ABC
from enum import Enum
from functools import partial
from typing import Set, Generator, List

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.constants import NucypherTokenConfig, NucypherMinerConfig
from web3.contract import Contract


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
        return r.format(class_name, self.blockchain, self.__contract)

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

    @property
    def origin(self) -> str:
        return self.blockchain.interface.w3.eth.coinbase    # TODO: make swappable

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        if address is None:
            address = self.contract_address
        return self.contract.functions.balanceOf(address).call()


class NucypherTokenAgent(EthereumContractAgent, NucypherTokenConfig):
    _principal_contract_name = "NuCypherToken"


class MinerAgent(EthereumContractAgent, NucypherMinerConfig):
    """
    Wraps NuCypher's Escrow solidity smart contract

    In order to become a participant of the network,
    a miner locks tokens by depositing to the Escrow contract address
    for a duration measured in periods.
    """

    _principal_contract_name = "MinersEscrow"

    class NotEnoughUrsulas(Exception):
        pass

    class MinerInfo(Enum):
        VALUE = 0
        DECIMALS = 1
        LAST_ACTIVE_PERIOD = 2
        CONFIRMED_PERIOD_1 = 3
        CONFIRMED_PERIOD_2 = 4

    def __init__(self, token_agent: NucypherTokenAgent, *args, **kwargs):
        super().__init__(blockchain=token_agent.blockchain, *args, **kwargs)
        self.token_agent = token_agent
        self.miners = list()    # Tracks per client

    def get_miner_ids(self) -> Set[str]:
        """
        Fetch all miner IDs from the local cache and return them in a set
        """

        return {miner.get_id() for miner in self.miners}

    def swarm(self) -> Generator[str, None, None]:
        """
        Returns an iterator of all miner addresses via cumulative sum, on-network.

        Miner addresses will be returned in the order in which they were added to the MinersEscrow's ledger
        """

        count = self.contract.functions.getMinersLength().call()
        for index in range(count):
            addr = self.contract.functions.miners(index).call()
            yield self.blockchain.interface.w3.toChecksumAddress(addr)

    def sample(self, quantity: int=10, additional_ursulas: float=1.7, attempts: int=5, duration: int=10) -> List[str]:
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
        n_tokens = self.contract.functions.getAllLockedTokens().call()

        if not n_tokens > 0:
            raise self.NotEnoughUrsulas('There are no locked tokens.')

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))
            deltas = [i-j for i, j in zip(points[1:], points[:-1])]

            addrs, addr, index, shift = set(), constants.NULL_ADDRESS, 0, 0
            for delta in deltas:
                addr, index, shift = self.contract.functions.findCumSum(index, delta + shift, duration).call()
                addrs.add(addr)

            if len(addrs) >= quantity:
                return system_random.sample(addrs, quantity)

        raise self.NotEnoughUrsulas('Selection failed after {} attempts'.format(attempts))


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
