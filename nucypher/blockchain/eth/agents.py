import random
from abc import ABC
from enum import Enum
from typing import Set, Generator, List, Tuple, Union

from web3.contract import Contract

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.chains import Blockchain
from constant_sorrow import constants


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

    @property
    def origin(self) -> str:
        return self.blockchain.interface.w3.eth.coinbase    # TODO: make swappable

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        address = address if address is not None else self.contract_address
        return self.contract.functions.balanceOf(address).call()


class NucypherTokenAgent(EthereumContractAgent):
    _principal_contract_name = "NuCypherToken"


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

    def swarm(self, fetch_data: bool=False) -> Union[Generator[str, None, None], Generator[Tuple[str, bytes], None, None]]:
        """
        Returns an iterator of all miner addresses via cumulative sum, on-network.
        if fetch_data is true, tuples containing the address and the miners stored data are yielded.

        Miner addresses are returned in the order in which they registered with the MinersEscrow contract's ledger
        """

        miner_population = self.contract.functions.getMinersLength().call()
        for index in range(miner_population):

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
        n_tokens = self.contract.functions.getAllLockedTokens().call()

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
