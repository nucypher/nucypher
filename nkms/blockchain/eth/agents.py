import random
from abc import ABC
from enum import Enum
from typing import Set, Generator, List

from functools import partial

from nkms.blockchain.eth.deployers import MinerEscrowDeployer, NuCypherKMSTokenDeployer, PolicyManagerDeployer, \
    ContractDeployer


class EthereumContractAgent(ABC):
    """
    Base class for ethereum contract wrapper types that interact with blockchain contract instances
    """

    _principal_contract_name = NotImplemented
    __contract_address = NotImplemented

    class ContractNotDeployed(ContractDeployer.ContractDeploymentError):
        pass

    def __init__(self, blockchain, *args, **kwargs):
        self.blockchain = blockchain

        address = blockchain.provider.get_contract_address(contract_name=self._principal_contract_name)[-1]  # TODO
        self._contract = blockchain.provider.get_contract(address)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self.blockchain, self._contract)

    def __eq__(self, other):
        return bool(self.contract_address == other.contract_address)

    @property
    def contract_address(self):
        return self._contract.address

    @property
    def contract_name(self) -> str:
        return self._principal_contract_name

    @property
    def origin(self) -> str:
        return self.blockchain.provider.w3.eth.coinbase    # TODO: make swappable

    def read(self):
        """
        Returns an object that exposes the contract instance functions.

        This method is intended for use with method chaining,
        results in zero state changes, and costs zero gas.
        Useful as a dry-run before sending an actual transaction.

        See more on interacting with contract instances in the Populus docs:
        http://populus.readthedocs.io/en/latest/dev_cycle.part-07.html#call-an-instance-function
        """
        return self._contract.call()

    def transact(self, payload: dict):
        """Packs kwargs into payload dictionary and transmits an eth contract transaction"""
        return self._contract.transact(payload)

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        if address is None:
            address = self.contract_address
        return self.read().balanceOf(address)


class NuCypherKMSTokenAgent(EthereumContractAgent):

    _deployer = NuCypherKMSTokenDeployer
    _principal_contract_name = NuCypherKMSTokenDeployer._contract_name


class MinerAgent(EthereumContractAgent):
    """
    Wraps NuCypher's Escrow solidity smart contract, and manages a... PopulusContract?

    In order to become a participant of the network,
    a miner locks tokens by depositing to the Escrow contract address
    for a duration measured in periods.
    """

    _deployer = MinerEscrowDeployer
    _principal_contract_name = MinerEscrowDeployer._contract_name

    class NotEnoughUrsulas(Exception):
        pass

    class MinerInfo(Enum):
        MINERS_LENGTH = 0
        MINER = 1
        VALUE = 2
        DECIMALS = 3
        LOCKED_VALUE = 4
        RELEASE = 5
        MAX_RELEASE_PERIODS = 6
        RELEASE_RATE = 7
        CONFIRMED_PERIODS_LENGTH = 8
        CONFIRMED_PERIOD = 9
        CONFIRMED_PERIOD_LOCKED_VALUE = 10
        LAST_ACTIVE_PERIOD_F = 11
        DOWNTIME_LENGTH = 12
        DOWNTIME_START_PERIOD = 13
        DOWNTIME_END_PERIOD = 14
        MINER_IDS_LENGTH = 15
        MINER_ID = 16

    def __init__(self, token_agent: NuCypherKMSTokenAgent):
        super().__init__(blockchain=token_agent.blockchain)  # TODO: public
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

        info_reader = partial(self.read().getMinerInfo,
                              self.MinerInfo.MINERS_LENGTH.value,
                              self._deployer._null_addr)

        count = info_reader(0).encode('latin-1')
        count = self.blockchain._chain.web3.toInt(count)

        for index in range(count):
            addr = info_reader(index).encode('latin-1')
            yield self.blockchain._chain.web3.toChecksumAddress(addr)

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
        n_tokens = self.read().getAllLockedTokens()

        if not n_tokens > 0:
            raise self.NotEnoughUrsulas('There are no locked tokens.')

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))
            deltas = [i-j for i, j in zip(points[1:], points[:-1])]

            addrs, addr, index, shift = set(), self._deployer._null_addr, 0, 0
            for delta in deltas:
                addr, index, shift = self.read().findCumSum(index, delta + shift, duration)
                addrs.add(addr)

            if len(addrs) >= quantity:
                return system_random.sample(addrs, quantity)

        raise self.NotEnoughUrsulas('Selection failed after {} attempts'.format(attempts))


class PolicyAgent(EthereumContractAgent):

    _deployer = PolicyManagerDeployer
    _principal_contract_name = PolicyManagerDeployer._contract_name

    def fetch_arrangement_data(self, arrangement_id: bytes) -> list:
        blockchain_record = self.read().policies(arrangement_id)
        return blockchain_record

    def revoke_arrangement(self, arrangement_id: bytes, author, gas_price: int):
        """
        Revoke by arrangement ID; Only the policy author can revoke the policy
        """

        txhash = self.transact({'from': author.address, 'gas_price': gas_price}).revokePolicy(arrangement_id)
        self.blockchain.wait_for_receipt(txhash)
        return txhash
