from abc import ABC, abstractmethod


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
        self.__contract = None
        self._blockchain = blockchain

    def __eq__(self, other):
        return self.__contract.address == other.address

    @property
    def address(self) -> str:
        return self.__contract.address

    @property
    def is_deployed(self) -> bool:
        return bool(self.__contract is not None)

    @property
    def is_armed(self) -> bool:
        return bool(self.__armed is True)

    @classmethod
    def contract_name(cls) -> str:
        return cls._contract_name

    def _verify_contract_deployment(self) -> None:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""
        if not self.__contract:
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

    # @classmethod
    # def from_blockchain(cls, blockchain: TheBlockchain) -> 'ContractDeployer':
    #     """
    #     Returns the NuCypherKMSToken object,
    #     or raises UnknownContract if the contract has not been deployed.
    #     """
    #     contract = blockchain._chain.provider.get_contract(cls.contract_name)
    #     instance = cls(blockchain=blockchain)
    #     instance._contract = contract
    #     return instance


class EthereumContractAgent(ABC):
    _deployer = NotImplemented
    _principal_contract_name = NotImplemented

    class ContractNotDeployed(Exception):
        pass

    def __init__(self, agent, *args, **kwargs):
        if not self._blockchain:
            self._blockchain = agent._blockchain

        contract = self._blockchain._chain.provider.get_contract(self._principal_contract_name)
        self.__contract = contract

    def __init_subclass__(cls, deployer):
        cls._deployer = deployer
        cls._principal_contract_name = deployer.contract_name()

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self._blockchain, self.__contract)

    def call(self):
        return self.__contract.call()

    def transact(self, *args, **kwargs):
        return self.__contract.transact(*args, **kwargs)

    @property
    def contract_address(self):
        return self.__contract.address

    @property
    def contract_name(self):
        return self._principal_contract_name
