import random
from typing import List

from populus.contracts.contract import PopulusContract

from nkms_eth.token import NuCypherKMSToken
from .blockchain import Blockchain

addr = str


class Escrow:
    _contract_name = 'MinersEscrow'
    hours_per_period = 1       # 24
    min_release_periods = 1    # 30
    max_awarded_periods = 365
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
        """Gateway to contract function calls"""
        return self.contract.call()

    def __eq__(self, other):
        return self.contract.address == other.contract.address

    def arm(self):
        self.armed = True
        return self

    def deploy(self):
        if not self.armed:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')
        if self.contract:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        contract, deploy_txhash = self.blockchain.chain.provider.deploy_contract(self._contract_name,
                                                          deploy_args=[self.token.contract.address] + self.mining_coeff,
                                                          deploy_transaction={'from': self.token.creator})

        self.blockchain.chain.wait.for_receipt(deploy_txhash, timeout=self.blockchain.timeout)
        self.contract = contract

        reward_txhash = self.token.transact({'from': self.token.creator}).transfer(self.contract.address, self.reward)
        self.blockchain.chain.wait.for_receipt(reward_txhash, timeout=self.blockchain.timeout)

        init_txhash = self.transact({'from': self.token.creator}).initialize()
        self.blockchain.chain.wait.for_receipt(init_txhash, timeout=self.blockchain.timeout)

        return deploy_txhash, reward_txhash, init_txhash

    @classmethod
    def get(cls, blockchain, token):
        """Returns an escrow object or an error"""
        contract = blockchain.chain.provider.get_contract(cls._contract_name)
        return cls(blockchain=blockchain, token=token, contract=contract)

    def transact(self, *args, **kwargs):
        if not self.contract:
            raise self.ContractDeploymentError('Contract must be deployed before executing transactions.')
        return self.contract.transact(*args, **kwargs)

    def get_dht(self) -> set:
        """Fetch all DHT keys and return them as a set"""
        return {miner.get_dht_key()for miner in self.miners}

    def sample(self, quantity: int=10, additional_ursulas: float=1.7, attempts: int=5, duration: int=10) -> List[addr]:
        """
        Select n random staking Ursulas, according to their stake distribution.
        The returned addresses are shuffled, so one can request more than needed and
        throw away those which do not respond.
        """

        system_random = random.SystemRandom()
        n_select = round(quantity*additional_ursulas)            # Select more Ursulas
        n_tokens = self.__call__().getAllLockedTokens()

        if not n_tokens:
            raise self.NotEnoughUrsulas('No locked tokens.')

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

