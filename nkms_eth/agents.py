import random
from abc import ABC
from typing import Set, Generator, List

from nkms_eth.deployers import MinerEscrowDeployer, NuCypherKMSTokenDeployer, PolicyManagerDeployer, ContractDeployer


class EthereumContractAgent(ABC):
    _principal_contract_name = NotImplemented

    _contract_subclasses = list()

    class ContractNotDeployed(ContractDeployer.ContractDeploymentError):
        pass

    def __init__(self, blockchain, *args, **kwargs):

        self._blockchain = blockchain
        self._contract = self.__fetch_contract()

    @classmethod
    def __init_subclass__(cls, deployer, **kwargs):
        """
        https://www.python.org/dev/peps/pep-0487/#proposal
        """
        super().__init_subclass__(**kwargs)
        cls._deployer = deployer
        cls._principal_contract_name = deployer._contract_name
        cls._contract_subclasses.append(cls)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self._blockchain, self._contract)

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
        return self._blockchain._chain.web3.eth.accounts[0]    # TODO: make swappable

    def __fetch_contract(self):
        contract = self._blockchain._chain.provider.get_contract(self._principal_contract_name)
        return contract

    def call(self):
        return self._contract.call()

    def transact(self, payload: dict):
        """Packs kwargs into payload dictionary and transmits an eth contract transaction"""
        return self._contract.transact(payload)

    def get_balance(self, address: str=None) -> int:
        """Get the balance of a token address, or of this contract address"""
        if address is None:
            address = self.contract_address
        return self.call().balanceOf(address)


class NuCypherKMSTokenAgent(EthereumContractAgent, deployer=NuCypherKMSTokenDeployer):

    _principal_contract_name = NotImplemented

    def registrar(self):
        """Retrieve all known addresses for this contract"""
        all_known_address = self._blockchain._chain.registrar.get_contract_address(self._principal_contract_name)
        return all_known_address


class MinerAgent(EthereumContractAgent, deployer=MinerEscrowDeployer):
    """
    Wraps NuCypher's Escrow solidity smart contract, and manages a PopulusContract.

    In order to become a participant of the network,
    a miner locks tokens by depositing to the Escrow contract address
    for a duration measured in periods.

    """

    class NotEnoughUrsulas(Exception):
        pass

    def __init__(self, token_agent: NuCypherKMSTokenAgent):
        super().__init__(blockchain=token_agent._blockchain)
        self.token_agent = token_agent
        self.miners = list()

    def get_miner_ids(self) -> Set[str]:
        """
        Fetch all miner IDs from the local cache and return them in a set
        """

        return {miner.get_id() for miner in self.miners}

    def swarm(self) -> Generator[str, None, None]:
        """
        Returns an iterator of all miner addresses via cumulative sum, on-network.
        """

        # TODO - Partial;
        count = self.call().getMinerInfo(self._deployer.MinerInfoField.MINERS_LENGTH.value, self._deployer._null_addr, 0).encode('latin-1')
        count = self._blockchain._chain.web3.toInt(count)

        for index in range(count):
            addr = self.call().getMinerInfo(self._deployer.MinerInfoField.MINER.value, self._deployer._null_addr, index).encode('latin-1')
            yield self._blockchain._chain.web3.toChecksumAddress(addr)

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
        n_tokens = self.call().getAllLockedTokens()

        if not n_tokens > 0:
            raise self.NotEnoughUrsulas('There are no locked tokens.')

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))
            deltas = [i-j for i, j in zip(points[1:], points[:-1])]

            addrs, addr, index, shift = set(), self._deployer._null_addr, 0, 0
            for delta in deltas:
                addr, index, shift = self.call().findCumSum(index, delta+shift, duration)
                addrs.add(addr)

            if len(addrs) >= quantity:
                return system_random.sample(addrs, quantity)

        raise self.NotEnoughUrsulas('Selection failed after {} attempts'.format(attempts))


class PolicyAgent(EthereumContractAgent, deployer=PolicyManagerDeployer):

    def __init__(self, miner_agent):
        super().__init__(blockchain=miner_agent._blockchain)
        self.miner_agent = miner_agent

    def fetch_arrangement_data(self, arrangement_id: bytes) -> list:
        blockchain_record = self.call().policies(arrangement_id)
        return blockchain_record

    def revoke_arrangement(self, arrangement_id: bytes, author, gas_price: int):
        """
        Revoke by arrangement ID; Only the policy author can revoke the policy
        """

        txhash = self.transact({'from': author.address, 'gas_price': gas_price}).revokePolicy(arrangement_id)
        self._blockchain.wait_for_receipt(txhash)
        return txhash
