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
    __contract_name = None

    class ContractDeploymentError(Exception):
        pass

    def __init__(self, blockchain):
        self._armed = False
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
    @classmethod
    def contract_name(cls) -> str:
        return cls.__contract_name

    def _verify_contract_deployment(self) -> None:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""
        if not self.__contract:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)
        return None

    def arm(self) -> None:
        self._armed = True
        return None

    @abstractmethod
    def deploy(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def make_agent(self) -> 'ContractAgent':
        raise NotImplementedError


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


class ContractAgent(ABC):
    __deployer = None
    _contract_name = None

    class ContractNotDeployed(Exception):
        pass

    def __init__(self, agent, *args, **kwargs):
        contract = agent._blockchain._chain.provider.get_contract(agent._contract_name)
        self._contract = contract
        self._blockchain = agent._blockchain

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(blockchain={}, contract={})"
        return r.format(class_name, self._blockchain, self._contract)

    def call(self):
        return self._contract.call()

    def transact(self, *args, **kwargs):
        return self._contract.transact(*args, **kwargs)
