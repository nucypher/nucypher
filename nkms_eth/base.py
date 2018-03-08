from abc import ABC, abstractmethod

from nkms_eth.blockchain import TheBlockchain


class Actor(ABC):
    def __init__(self, address):
        if isinstance(address, bytes):
            address = address.hex()
        self.address = address

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r.format(class_name, self.address)
        return r


class ContractDeployer(ABC):

    _contract_name = NotImplemented

    class ContractDeploymentError(Exception):
        pass

    def __init__(self, blockchain):
        self.__armed = False
        self._contract = None

        # Sanity check
        if not isinstance(blockchain, TheBlockchain):
            error = 'Only TheBlockchain can be used to create a deployer, got {}.'
            raise ValueError(error.format(type(blockchain)))
        self._blockchain = blockchain

    def __eq__(self, other):
        return self._contract.address == other.address

    @property
    def contract_address(self) -> str:
        try:
            address = self._contract.address
        except AttributeError:
            cls = self.__class__
            raise cls.ContractDeploymentError('Contract not deployed')
        else:
            return address

    @property
    def is_deployed(self) -> bool:
        return bool(self._contract is not None)

    @property
    def is_armed(self) -> bool:
        return bool(self.__armed is True)

    def _verify_contract_deployment(self) -> None:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""
        if not self._contract:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)
        return None

    def arm(self) -> None:
        self.__armed = True
        return None

    @abstractmethod
    def deploy(self) -> str:
        raise NotImplementedError

    # TODO
    # @abstractmethod
    # def make_agent(self) -> 'EthereumContractAgent':
    #     raise NotImplementedError

    @classmethod
    def from_blockchain(cls, blockchain: TheBlockchain) -> 'ContractDeployer':
        """
        Returns the NuCypherKMSToken object,
        or raises UnknownContract if the contract has not been deployed.
        """
        contract = blockchain._chain.provider.get_contract(cls._contract_name)
        instance = cls(blockchain=blockchain)
        instance._contract = contract
        return instance


class EthereumContractAgent(ABC):
    _deployer = NotImplemented
    _principal_contract_name = NotImplemented

    class ContractNotDeployed(ContractDeployer.ContractDeploymentError):
        pass

    def __init__(self, agent, *args, **kwargs):

        self._blockchain = agent._blockchain

        contract = self._blockchain._chain.provider.get_contract(self._principal_contract_name)
        self._contract = contract

    @classmethod
    def __init_subclass__(cls, deployer, **kwargs):
        """
        https://www.python.org/dev/peps/pep-0487/#proposal
        """
        cls._deployer = deployer
        cls._principal_contract_name = deployer._contract_name
        super().__init_subclass__(**kwargs)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self._blockchain, self._contract)

    def __eq__(self, other):
        return bool(self.contract_address == other.contract_address)

    def call(self):
        return self._contract.call()

    def transact(self, *args, **kwargs):
        return self._contract.transact(*args, **kwargs)

    @property
    def origin(self):
        return self._blockchain._chain.web3.eth.accounts[0]    # TODO

    @property
    def contract_address(self):
        return self._contract.address

    @property
    def contract_name(self):
        return self._principal_contract_name
