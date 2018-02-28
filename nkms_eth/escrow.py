import random
from typing import List, Tuple, Set, Generator

from populus.contracts.contract import PopulusContract

from nkms_eth.token import NuCypherKMSToken
from .blockchain import Blockchain

addr = str


class Escrow:
    """
    In order to become a participant of the network,
    a miner locks tokens by depositing to the Escrow contract
    for a duration measured in periods.

    The contract must be armed, before it can be deployed
    to the blockchain.
    """

    _contract_name = 'MinersEscrow'
    hours_per_period = 1       # 24 Hours
    min_release_periods = 1    # 30 Periods
    max_awarded_periods = 365  # Periods
    min_allowed_locked = 10 ** 6
    max_allowed_locked = 10 ** 7 * NuCypherKMSToken.M
    reward = NuCypherKMSToken.saturation - NuCypherKMSToken.premine
    null_addr = '0x' + '0' * 40

    mining_coeff = [
        hours_per_period,
        2 * 10 ** 7,
        max_awarded_periods,
        max_awarded_periods,
        min_release_periods,
        min_allowed_locked,
        max_allowed_locked
    ]

    class ContractDeploymentError(Exception):
        pass

    class NotEnoughUrsulas(Exception):
        pass

    def __init__(self, blockchain: Blockchain, token: NuCypherKMSToken, contract: PopulusContract=None):
        self.blockchain = blockchain
        self.contract = contract
        self.token = token
        self.armed = False
        self.miners = list()

    def __call__(self):
        """Gateway to contract function calls without state change."""
        return self.contract.call()

    def __eq__(self, other: 'Escrow'):
        """If two deployed escrows have the same contract address, they are equal."""
        return self.contract.address == other.contract.address

    def arm(self) -> None:
        self.armed = True

    def deploy(self) -> Tuple[str, str, str]:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!

        Returns transaction hashes in a tuple: deploy, reward, and initialize.
        """

        if self.armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self.contract is not None:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        the_escrow_contract, deploy_txhash = self.blockchain._chain.provider.deploy_contract(self._contract_name,
                                                          deploy_args=[self.token.contract.address] + self.mining_coeff,
                                                          deploy_transaction={'from': self.token.creator})

        self.blockchain._chain.wait.for_receipt(deploy_txhash, timeout=self.blockchain._timeout)
        self.contract = the_escrow_contract

        reward_txhash = self.token.transact({'from': self.token.creator}).transfer(self.contract.address, self.reward)
        self.blockchain._chain.wait.for_receipt(reward_txhash, timeout=self.blockchain._timeout)

        init_txhash = self.contract.transact({'from': self.token.creator}).initialize()
        self.blockchain._chain.wait.for_receipt(init_txhash, timeout=self.blockchain._timeout)

        return deploy_txhash, reward_txhash, init_txhash

    @classmethod
    def get(cls, blockchain, token) -> 'Escrow':
        """
        Returns the Escrow object,
        or raises UnknownContract if the contract has not been deployed.
        """
        contract = blockchain._chain.provider.get_contract(cls._contract_name)
        return cls(blockchain=blockchain, token=token, contract=contract)

    def transact(self, *args, **kwargs):
        if self.contract is None:
            raise self.ContractDeploymentError('Contract must be deployed before executing transactions.')
        return self.contract.transact(*args, **kwargs)

    def get_dht(self) -> Set[str]:
        """Fetch all miner IDs and return them in a set"""
        return {miner.get_id() for miner in self.miners}

    def swarm(self) -> Generator[str, None, None]:
        """
        Generates all miner addresses via cumulative sum.
        """
        miner, i = self.null_addr, 0
        while True:

            # Get the next miner
            next_miner = self.__call__().getNextMiner(miner)

            if next_miner == self.null_addr:
                raise StopIteration()

            yield next_miner

            # Advance
            miner = next_miner
            i += 1

    def sample(self, quantity: int=10, additional_ursulas: float=1.7, attempts: int=5, duration: int=10) -> List[addr]:
        """
        Select n random staking Ursulas, according to their stake distribution.
        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.

                     _start
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stop
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
        n_tokens = self.__call__().getAllLockedTokens()

        if not n_tokens > 0:
            raise self.NotEnoughUrsulas('There are no locked tokens.')

        for _ in range(attempts):
            points = [0] + sorted(system_random.randrange(n_tokens) for _ in range(n_select))
            deltas = [i-j for i, j in zip(points[1:], points[:-1])]

            addrs, addr, shift = set(), self.null_addr, 0
            for delta in deltas:
                addr, shift = self.__call__().findCumSum(addr, delta+shift, duration)
                addrs.add(addr)

            if len(addrs) >= quantity:
                return system_random.sample(addrs, quantity)

        raise self.NotEnoughUrsulas('Selection failed after {} attempts'.format(attempts))

