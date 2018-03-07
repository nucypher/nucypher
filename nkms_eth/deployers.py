from typing import Tuple

from nkms_eth.agents import MinerAgent
from nkms_eth.base import ContractDeployer
from nkms_eth.token import NuCypherKMSTokenAgent
from .blockchain import TheBlockchain

addr = str


class NuCypherKMSTokenDeployer(ContractDeployer):
    __contract_name = 'NuCypherKMSToken'
    __subdigits = 18
    _M = 10 ** __subdigits
    __premine = int(1e9) * _M
    __saturation = int(1e10) * _M
    _reward = __saturation - __premine

    def __init__(self, blockchain: TheBlockchain):
        super().__init__(blockchain=blockchain)
        self.__creator = self._blockchain._chain.web3.eth.accounts[0]

    @property
    def origin(self):
        return self.__creator

    def deploy(self) -> str:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!
        """

        if self._armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self._contract is not None:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        the_nucypherKMS_token_contract, deployment_txhash = self._blockchain._chain.provider.deploy_contract(
            self.__contract_name,
            deploy_args=[self.__saturation],
            deploy_transaction={'from': self.origin})

        self._blockchain._chain.wait.for_receipt(deployment_txhash, timeout=self._blockchain._timeout)

        self._contract = the_nucypherKMS_token_contract
        return deployment_txhash

    def _airdrop(self, amount: int):
        """Airdrops from creator address to all other addresses!"""

        _creator, *addresses = self._blockchain._chain.web3.eth.accounts

        def txs():
            for address in addresses:
                yield self._contract.transact({'from': self.origin}).transfer(address, amount * (10 ** 6))

        for tx in txs():
            self._blockchain._chain.wait.for_receipt(tx, timeout=10)

        return self


class PolicyManagerDeployer(ContractDeployer):

    __contract_name = 'PolicyManager'

    def __init__(self, escrow: MinerAgent):
        super().__init__(escrow)
        self.escrow = escrow
        self.token = escrow._token

    def deploy(self) -> Tuple[str, str]:
        if self.armed is False:
            raise self.ContractDeploymentError('PolicyManager contract not armed')
        if self.is_deployed is True:
            raise self.ContractDeploymentError('PolicyManager contract already deployed')

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self.blockchain._chain.provider.deploy_contract(
            self.__contract_name,
            deploy_args=[self.escrow._contract.address],
            deploy_transaction={'from': self.token.creator})

        self._contract = the_policy_manager_contract

        set_txhash = self.escrow.transact({'from': self.token.creator}).setPolicyManager(the_policy_manager_contract.address)
        self.blockchain._chain.wait.for_receipt(set_txhash)

        return deploy_txhash, set_txhash



class MinerEscrowDeployer(ContractDeployer):

    __contract_name = 'MinersEscrow'
    __hours_per_period = 1       # 24 Hours    TODO
    __min_release_periods = 1    # 30 Periods
    __max_awarded_periods = 365  # Periods
    __min_allowed_locked = 10 ** 6
    __max_allowed_locked = 10 ** 7 * NuCypherKMSTokenDeployer._M
    __reward = NuCypherKMSTokenDeployer._reward
    __null_addr = '0x' + '0' * 40

    __mining_coeff = [
        __hours_per_period,
        2 * 10 ** 7,
        __max_awarded_periods,
        __max_awarded_periods,
        __min_release_periods,
        __min_allowed_locked,
        __max_allowed_locked
    ]

    def __init__(self, token: NuCypherKMSTokenAgent):
        super().__init__(token)
        self._token = token

    @property
    @classmethod
    def null_address(cls):
        return cls.__null_addr

    def deploy(self) -> Tuple[str, str, str]:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!

        Returns transaction hashes in a tuple: deploy, reward, and initialize.
        """

        if self._armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self._contract is not None:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        the_escrow_contract, deploy_txhash = self._blockchain._chain.provider.deploy_contract(self.__contract_name,
                                                                                              deploy_args=[self._token._contract.address] + self.__mining_coeff,
                                                                                              deploy_transaction={'from': self._token._creator})

        self._blockchain._chain.wait.for_receipt(deploy_txhash, timeout=self._blockchain._timeout)
        self._contract = the_escrow_contract

        reward_txhash = self._token.transact({'from': self._token.origin}).transfer(self._contract.address, self.__reward)
        self._blockchain._chain.wait.for_receipt(reward_txhash, timeout=self._blockchain._timeout)

        init_txhash = self._contract.transact({'from': self._token.origin}).initialize()
        self._blockchain._chain.wait.for_receipt(init_txhash, timeout=self._blockchain._timeout)

        return deploy_txhash, reward_txhash, init_txhash
