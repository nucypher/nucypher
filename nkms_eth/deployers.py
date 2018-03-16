from typing import Tuple

from nkms_eth.base import ContractDeployer
from nkms_eth.config import NuCypherMinerConfig, NuCypherTokenConfig
from .blockchain import TheBlockchain

addr = str


class NuCypherKMSTokenDeployer(ContractDeployer, NuCypherTokenConfig):

    _contract_name = 'NuCypherKMSToken'

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

        if self.is_armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self.is_deployed is True:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        the_nucypher_token_contract, deployment_txhash = self._blockchain._chain.provider.deploy_contract(
            self._contract_name,
            deploy_args=[self.saturation],
            deploy_transaction={'from': self.origin})

        self._blockchain._chain.wait.for_receipt(deployment_txhash, timeout=self._blockchain._timeout)
        self._contract = the_nucypher_token_contract

        return deployment_txhash


class PolicyManagerDeployer(ContractDeployer):

    _contract_name = 'PolicyManager'

    def __init__(self, miner_agent):
        super().__init__(miner_agent)
        self.miner_agent = miner_agent
        self.token_agent = miner_agent._token_agent

    def deploy(self) -> Tuple[str, str]:
        if self.is_armed is False:
            raise self.ContractDeploymentError('PolicyManager contract not armed')
        if self.is_deployed is True:
            raise self.ContractDeploymentError('PolicyManager contract already deployed')

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self._blockchain._chain.provider.deploy_contract(
            self._contract_name,
            deploy_args=[self.miner_agent._contract.address],
            deploy_transaction={'from': self.token_agent.creator})

        self._contract = the_policy_manager_contract

        set_txhash = self.miner_agent.transact({'from': self.token_agent.creator}).setPolicyManager(the_policy_manager_contract.address)
        self._blockchain._chain.wait.for_receipt(set_txhash)

        return deploy_txhash, set_txhash


class MinerEscrowDeployer(ContractDeployer, NuCypherMinerConfig):

    _contract_name = 'MinersEscrow'

    def __init__(self, token_agent):
        self._token_agent = token_agent
        super().__init__(blockchain=token_agent._blockchain)

    def deploy(self) -> Tuple[str, str, str]:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!

        Returns transaction hashes in a tuple: deploy, reward, and initialize.
        """

        if self.is_armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self.is_deployed is True:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        deploy_args = [self._token_agent._contract.address] + self.mining_coefficient
        deploy_tx = {'from': self._token_agent.origin}

        the_escrow_contract, deploy_txhash = self._blockchain._chain.provider.deploy_contract(self._contract_name,
                                                                                              deploy_args=deploy_args,
                                                                                              deploy_transaction=deploy_tx)

        self._blockchain._chain.wait.for_receipt(deploy_txhash, timeout=self._blockchain._timeout)
        self._contract = the_escrow_contract

        reward_txhash = self._token_agent.transact({'from': self._token_agent.origin}).transfer(self.contract_address,
                                                                                                self.reward)
        self._blockchain._chain.wait.for_receipt(reward_txhash, timeout=self._blockchain._timeout)

        init_txhash = self._contract.transact({'from': self._token_agent.origin}).initialize()
        self._blockchain._chain.wait.for_receipt(init_txhash, timeout=self._blockchain._timeout)

        return deploy_txhash, reward_txhash, init_txhash
