from constant_sorrow.constants import CONTRACT_NOT_DEPLOYED, NO_DEPLOYER_CONFIGURED
from eth_utils import is_checksum_address
from typing import Tuple, Dict

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.agents import (
    EthereumContractAgent,
    MinerAgent,
    NucypherTokenAgent,
    PolicyAgent,
    UserEscrowAgent
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from .chains import Blockchain


class ContractDeployer:

    agency = NotImplemented
    _interface_class = BlockchainDeployerInterface
    _contract_name = NotImplemented

    class ContractDeploymentError(Exception):
        pass

    class ContractNotDeployed(ContractDeploymentError):
        pass

    def __init__(self,
                 deployer_address: str,
                 blockchain: Blockchain = None,
                 ) -> None:

        self.__armed = False
        self._contract = CONTRACT_NOT_DEPLOYED
        self.deployment_receipt = CONTRACT_NOT_DEPLOYED
        self.__proxy_contract = NotImplemented
        self.__deployer_address = deployer_address

        # Sanity check
        if blockchain is not None:
            if not isinstance(blockchain, Blockchain):
                error = 'Only a Blockchain instance can be used to create a deployer; Got {}.'
                raise ValueError(error.format(type(blockchain)))

        self.blockchain = blockchain or Blockchain.connect()

    @property
    def contract_address(self) -> str:
        if self._contract is CONTRACT_NOT_DEPLOYED:
            raise self.ContractNotDeployed
        address = self._contract.address  # type: str
        return address

    @property
    def deployer_address(self):
        return self.__deployer_address

    @property
    def contract(self):
        return self._contract

    @property
    def dispatcher(self):
        return self.__proxy_contract

    @property
    def is_deployed(self) -> bool:
        return bool(self._contract is not CONTRACT_NOT_DEPLOYED)

    @property
    def is_armed(self) -> bool:
        return bool(self.__armed is True)

    def check_ready_to_deploy(self, fail=False, check_arming=False) -> Tuple[bool, list]:
        """
        Iterates through a set of rules required for an ethereum
        contract deployer to be eligible for deployment returning a
        tuple or raising an exception if <fail> is True.

        Returns a tuple containing the boolean readiness result and a list of reasons (if any)
        why the deployer is not ready.

        If fail is set to True, raise a configuration error, instead of returning.
        """

        rules = [
            (self.is_deployed is not True, 'Contract already deployed'),
            (self.deployer_address is not None, 'No deployer address set.'),
            (self.deployer_address is not NO_DEPLOYER_CONFIGURED, 'No deployer address set.'),
        ]

        if check_arming:
            rules.append((self.is_armed is True, 'Contract not armed'))

        disqualifications = list()
        for failed_rule, failure_reason in rules:
            if failed_rule is False:                           # If this rule fails...
                if fail is True:
                    raise self.ContractDeploymentError(failure_reason)
                else:
                    disqualifications.append(failure_reason)   # ... here's why
                    continue

        is_ready = True if len(disqualifications) == 0 else False
        return is_ready, disqualifications

    def _ensure_contract_deployment(self) -> bool:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""

        if self._contract is CONTRACT_NOT_DEPLOYED:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)

        return True

    def arm(self, abort=True) -> tuple:
        """
        Safety mechanism for ethereum contract deployment

        If the blockchain network being deployed is not in the testchains tuple,
        user interaction is required to enter the arming word.

        If fail_on_abort is True, raise a configuration Error if the user
        incorrectly types the arming_word.

        """
        if self.__armed is True and abort is True:
            raise self.ContractDeploymentError('{} deployer is already armed.'.format(self._contract_name))
        self.__armed, disqualifications = self.check_ready_to_deploy(fail=abort, check_arming=False)
        return self.__armed, disqualifications

    def deploy(self) -> dict:
        """
        Used after arming the deployer;
        Provides for the setup, deployment, and initialization of ethereum smart contracts.
        Emits the configured blockchain network transactions for single contract instance publication.
        """
        raise NotImplementedError

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(blockchain=self.blockchain, contract=self._contract)
        return agent


class NucypherTokenDeployer(ContractDeployer):

    agency = NucypherTokenAgent
    _contract_name = agency.principal_contract_name

    def __init__(self, deployer_address: str, *args, **kwargs) -> None:
        super().__init__(deployer_address=deployer_address, *args, **kwargs)
        self._creator = deployer_address

    def deploy(self) -> dict:
        """
        Deploy and publish the NuCypher Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!
        """
        self.check_ready_to_deploy(fail=True, check_arming=True)

        _contract, deployment_txhash = self.blockchain.interface.deploy_contract(
                                       self._contract_name,
                                       constants.TOKEN_SATURATION)

        self._contract = _contract
        return {'txhash': deployment_txhash}


class DispatcherDeployer(ContractDeployer):
    """
    Ethereum smart contract that acts as a proxy to another ethereum contract,
    used as a means of "dispatching" the correct version of the contract to the client
    """

    _contract_name = 'Dispatcher'

    def __init__(self, target_contract, secret_hash: bytes, *args, **kwargs):
        self.target_contract = target_contract
        self.secret_hash = secret_hash
        super().__init__(*args, **kwargs)

    def deploy(self) -> dict:

        dispatcher_contract, txhash = self.blockchain.interface.deploy_contract(self._contract_name,
                                                                                self.target_contract.address,
                                                                                self.secret_hash)

        self._contract = dispatcher_contract
        return {'txhash': txhash}


class MinerEscrowDeployer(ContractDeployer):
    """
    Deploys the MinerEscrow ethereum contract to the blockchain.  Depends on NucypherTokenAgent
    """

    agency = MinerAgent
    _contract_name = agency.principal_contract_name

    def __init__(self, token_agent, secret_hash, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_agent = token_agent
        self.secret_hash = secret_hash

    def __check_policy_manager(self):
        result = self.contract.functions.policyManager().call()
        if result is constants.NULL_ADDRESS:
            raise RuntimeError("PolicyManager contract is not initialized.")

    def deploy(self) -> dict:
        """
        Deploy and publish the NuCypher Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!

        Emits the folowing blockchain network transactions:
            - MinerEscrow contract deployment
            - MinerEscrow dispatcher deployment
            - Transfer reward tokens origin -> MinerEscrow contract
            - MinerEscrow contract initialization

        Returns transaction hashes in a dict.
        """

        # Raise if not all-systems-go
        self.check_ready_to_deploy(fail=True, check_arming=True)

        # Build deployment arguments
        origin_args = {'from': self.deployer_address}

        # 1 - Deploy #
        the_escrow_contract, deploy_txhash, = \
            self.blockchain.interface.deploy_contract(self._contract_name,
                                                      self.token_agent.contract_address,
                                                      *map(int, constants.MINING_COEFFICIENT))

        # 2 - Deploy the dispatcher used for updating this contract #
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=the_escrow_contract,
                                                 deployer_address=self.deployer_address,
                                                 secret_hash=self.secret_hash)

        dispatcher_deployer.arm()
        dispatcher_deploy_txhash = dispatcher_deployer.deploy()

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer.contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract
        wrapped_escrow_contract = self.blockchain.interface._wrap_contract(dispatcher_contract,
                                                                           target_contract=the_escrow_contract)

        # Switch the contract for the wrapped one
        the_escrow_contract = wrapped_escrow_contract

        # 3 - Transfer tokens to the miner escrow #
        reward_txhash = self.token_agent.contract.functions.transfer(the_escrow_contract.address,
                                                                     constants.TOKEN_SUPPLY).transact(origin_args)

        _reward_receipt = self.blockchain.wait_for_receipt(reward_txhash)

        # 4 - Initialize the Miner Escrow contract
        init_txhash = the_escrow_contract.functions.initialize().transact(origin_args)
        _init_receipt = self.blockchain.wait_for_receipt(init_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deploy': deploy_txhash,
                                   'dispatcher_deploy': dispatcher_deploy_txhash,
                                   'reward_transfer': reward_txhash,
                                   'initialize': init_txhash}

        # Set the contract and transaction hashes #
        self._contract = the_escrow_contract
        self.deployment_transactions = deployment_transactions
        return deployment_transactions

    def make_agent(self) -> EthereumContractAgent:
        self.__check_policy_manager()  # Ensure the PolicyManager contract has already been initialized
        agent = self.agency(token_agent=self.token_agent, contract=self._contract)
        return agent


class PolicyManagerDeployer(ContractDeployer):
    """
    Depends on MinerAgent and NucypherTokenAgent
    """

    agency = PolicyAgent
    _contract_name = agency.principal_contract_name

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(miner_agent=self.miner_agent, contract=self._contract)
        return agent

    def __init__(self, miner_agent, secret_hash, *args, **kwargs):
        self.token_agent = miner_agent.token_agent
        self.miner_agent = miner_agent
        self.secret_hash = secret_hash
        super().__init__(*args, **kwargs)

    def deploy(self) -> Dict[str, str]:
        self.check_ready_to_deploy(fail=True, check_arming=True)

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self.blockchain.interface.deploy_contract(
            self._contract_name, self.miner_agent.contract_address)

        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=the_policy_manager_contract,
                                                 deployer_address=self.deployer_address,
                                                 secret_hash=self.secret_hash)

        dispatcher_deployer.arm()
        dispatcher_deploy_txhash = dispatcher_deployer.deploy()

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer.contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract
        wrapped_policy_manager_contract = self.blockchain.interface._wrap_contract(dispatcher_contract,
                                                                                   target_contract=the_policy_manager_contract)

        # Switch the contract for the wrapped one
        the_policy_manager_contract = wrapped_policy_manager_contract

        # Configure the MinerEscrow by setting the PolicyManager
        policy_setter_txhash = self.miner_agent.contract.functions. \
            setPolicyManager(the_policy_manager_contract.address).transact({'from': self.deployer_address})

        self.blockchain.wait_for_receipt(policy_setter_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deployment': deploy_txhash,
                                   'dispatcher_deployment': dispatcher_deploy_txhash,
                                   'set_policy_manager': policy_setter_txhash}

        self.deployment_transactions = deployment_transactions
        self._contract = the_policy_manager_contract

        return deployment_transactions


class UserEscrowProxyDeployer(ContractDeployer):

    _contract_name = 'UserEscrowProxy'
    _linker_name = 'UserEscrowLibraryLinker'

    def __init__(self, policy_agent: PolicyAgent, secret_hash: bytes, *args, **kwargs):
        self.policy_agent = policy_agent
        self.miner_agent = policy_agent.miner_agent
        self.token_agent = policy_agent.token_agent
        self.secret_hash = secret_hash
        super().__init__(*args, **kwargs)

    def deploy(self) -> dict:

        deployment_transactions = dict()

        # Proxy
        proxy_args = (self._contract_name,
                      self.token_agent.contract_address,
                      self.miner_agent.contract_address,
                      self.policy_agent.contract_address)
        proxy_contract, proxy_deployment_txhash = self.blockchain.interface.deploy_contract(*proxy_args)
        self.__proxy = proxy_contract
        deployment_transactions['proxy_deployment'] = proxy_deployment_txhash

        # Linker
        linker_args = (self._linker_name, proxy_contract.address, self.secret_hash)
        linker_contract, linker_deployment_txhash = self.blockchain.interface.deploy_contract(*linker_args)
        self.__linker = linker_contract
        deployment_transactions['linker_deployment'] = linker_deployment_txhash
        return deployment_transactions


class UserEscrowDeployer(ContractDeployer):

    agency = UserEscrowAgent
    _contract_name = agency.principal_contract_name

    __proxy_name = UserEscrowProxyDeployer._contract_name
    __linker_name = UserEscrowProxyDeployer._linker_name

    def __init__(self,
                 policy_agent: PolicyAgent,
                 *args, **kwargs
                 ) -> None:

        self.policy_agent = policy_agent
        self.miner_agent = policy_agent.miner_agent
        self.token_agent = policy_agent.token_agent
        super().__init__(*args, **kwargs)

        try:
            self.__linker_contract = self.blockchain.interface.get_contract_by_name(name=self.__linker_name)
            self.__proxy_contract = self.blockchain.interface.get_contract_by_name(name=self.__proxy_name)
        except self.blockchain.interface.registry.UnknownContract:
            self.__linker_contract = CONTRACT_NOT_DEPLOYED
            self.__proxy_contract = CONTRACT_NOT_DEPLOYED

    def commit_beneficiary(self, beneficiary_address: str) -> str:
        if not is_checksum_address(beneficiary_address):
            raise self.ContractDeploymentError("{} is not a valid checksum address.".format(beneficiary_address))
        txhash = self.contract.functions.transferOwnership(beneficiary_address).transact({'from': self.deployer_address})
        self.blockchain.wait_for_receipt(txhash)
        return txhash

    def deploy(self, beneficiary_address: str = None) -> dict:
        if beneficiary_address:
            if not is_checksum_address(beneficiary_address):
                raise self.ContractDeploymentError('{} is not a valid checksum address'.format(beneficiary_address))

        self.check_ready_to_deploy(fail=True, check_arming=True)

        deployment_transactions = dict()

        args = ('UserEscrow', self.__linker_contract.address, self.token_agent.contract_address)
        user_escrow_contract, deploy_txhash = self.blockchain.interface.deploy_contract(*args)
        deployment_transactions['deploy_user_escrow'] = deploy_txhash

        if beneficiary_address:
            txhash = user_escrow_contract.functions.transferOwnership(beneficiary_address).transact({'from': self.deployer_address})
            deployment_transactions['transfer_ownership'] = txhash

        # Wrap the escrow contract (Govern)
        wrapped_user_escrow_contract = self.blockchain.interface._wrap_contract(wrapper_contract=self.__proxy_contract,
                                                                                target_contract=user_escrow_contract)

        # Switch the contract for the wrapped one
        user_escrow_contract = wrapped_user_escrow_contract
        self._contract = user_escrow_contract

        return deployment_transactions

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(policy_agent=self.policy_agent,
                            contract=self._contract)
        return agent