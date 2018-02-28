from populus.contracts.contract import PopulusContract
from .blockchain import Blockchain


class NuCypherKMSToken:
    _contract_name = 'NuCypherKMSToken'
    subdigits = 18
    M = 10 ** subdigits
    premine = int(1e9) * M
    saturation = int(1e10) * M

    class ContractDeploymentError(Exception):
        pass

    def __init__(self, blockchain: Blockchain, token_contract: PopulusContract=None):
        self.creator = blockchain._chain.web3.eth.accounts[0]
        self.blockchain = blockchain
        self.contract = token_contract
        self.armed = False

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self.blockchain, self.contract)

    def __eq__(self, other):
        """Two token objects are equal if they have the same contract address"""
        return self.contract.address == other.contract.address

    def __call__(self, *args, **kwargs):
        """Invoke contract -> No state change"""
        return self.contract.call(*args, **kwargs)

    def _check_contract_deployment(self) -> None:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""
        if not self.contract:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)

    def arm(self) -> None:
        """Arm contract for deployment to blockchain."""
        self.armed = True

    def deploy(self) -> str:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!
        """

        if self.armed is False:
            raise self.ContractDeploymentError('use .arm() to arm the contract, then .deploy().')

        if self.contract is not None:
            class_name = self.__class__.__name__
            message = '{} contract already deployed, use .get() to retrieve it.'.format(class_name)
            raise self.ContractDeploymentError(message)

        the_nucypherKMS_token_contract, deployment_txhash = self.blockchain._chain.provider.deploy_contract(
            self._contract_name,
            deploy_args=[self.saturation],
            deploy_transaction={'from': self.creator})

        self.blockchain._chain.wait.for_receipt(deployment_txhash, timeout=self.blockchain._timeout)

        self.contract = the_nucypherKMS_token_contract
        return deployment_txhash

    def transact(self, *args):
        """Invoke contract -> State change"""
        self._check_contract_deployment()
        result = self.contract.transact(*args)
        return result

    @classmethod
    def get(cls, blockchain):
        """
        Returns the NuCypherKMSToken object,
        or raises UnknownContract if the contract has not been deployed.
        """
        contract = blockchain._chain.provider.get_contract(cls._contract_name)
        return cls(blockchain=blockchain, token_contract=contract)

    def registrar(self):
        """Retrieve all known addresses for this contract"""
        self._check_contract_deployment()
        return self.blockchain._chain.registrar.get_contract_address(self._contract_name)

    def balance(self, address: str):
        """Get the balance of a token address"""
        self._check_contract_deployment()
        return self.__call__().balanceOf(address)

    def _airdrop(self, amount: int):
        """Airdrops from creator address to all other addresses!"""
        self._check_contract_deployment()
        _, *addresses = self.blockchain._chain.web3.eth.accounts

        def txs():
            for address in addresses:
                yield self.transact({'from': self.creator}).transfer(address, amount*(10**6))

        for tx in txs():
            self.blockchain._chain.wait.for_receipt(tx, timeout=10)

        return self
