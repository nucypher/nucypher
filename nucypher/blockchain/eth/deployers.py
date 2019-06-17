"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from eth_tester.exceptions import TransactionFailed
from eth_utils import is_checksum_address
from typing import Tuple, Dict
from web3.contract import Contract

from constant_sorrow.constants import CONTRACT_NOT_DEPLOYED, NO_DEPLOYER_CONFIGURED, NO_BENEFICIARY

from nucypher.blockchain.economics import TokenEconomics, SlashingEconomics
from nucypher.blockchain.eth.agents import (
    EthereumContractAgent,
    StakingEscrowAgent,
    NucypherTokenAgent,
    PolicyAgent,
    UserEscrowAgent,
    AdjudicatorAgent)

from nucypher.blockchain.eth.interfaces import BlockchainDeployer
from nucypher.blockchain.eth.registry import AllocationRegistry
from .interfaces import Blockchain


class ContractDeployer:

    agency = NotImplemented
    contract_name = NotImplemented
    _interface_class = BlockchainDeployer
    _upgradeable = NotImplemented
    __proxy_deployer = NotImplemented

    class ContractDeploymentError(Exception):
        pass

    class ContractNotDeployed(ContractDeploymentError):
        pass

    def __init__(self, deployer_address: str, blockchain: Blockchain) -> None:

        self.blockchain = blockchain
        self.deployment_transactions = CONTRACT_NOT_DEPLOYED
        self.deployment_receipt = CONTRACT_NOT_DEPLOYED
        self._contract = CONTRACT_NOT_DEPLOYED
        self.__proxy_contract = NotImplemented
        self.__deployer_address = deployer_address
        self.__ready_to_deploy = False

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
    def ready_to_deploy(self) -> bool:
        return bool(self.__ready_to_deploy is True)

    def check_deployment_readiness(self, fail=True) -> Tuple[bool, list]:
        """
        Iterates through a set of rules required for an ethereum
        contract deployer to be eligible for deployment returning a
        tuple or raising an exception if <fail> is True.

        Returns a tuple containing the boolean readiness result and a list of reasons (if any)
        why the deployer is not ready.

        If fail is set to True, raise a configuration error, instead of returning.
        """

        if self.__ready_to_deploy is True:
            return True, list()

        rules = [
            (self.is_deployed is not True, 'Contract already deployed'),
            (self.deployer_address is not None, 'No deployer address set.'),
            (self.deployer_address is not NO_DEPLOYER_CONFIGURED, 'No deployer address set.'),
        ]

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
        """Raises ContractDeploymentError if the contract has not been deployed."""

        if self._contract is CONTRACT_NOT_DEPLOYED:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed.'.format(class_name)
            raise self.ContractDeploymentError(message)
        return True

    def deploy(self, secret_hash: bytes, gas_limit: int) -> dict:
        """
        Provides for the setup, deployment, and initialization of ethereum smart contracts.
        Emits the configured blockchain network transactions for single contract instance publication.
        """
        raise NotImplementedError

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(blockchain=self.blockchain, contract=self._contract)
        return agent


class NucypherTokenDeployer(ContractDeployer):

    agency = NucypherTokenAgent
    contract_name = agency.registry_contract_name
    _upgradeable = False

    def __init__(self,
                 deployer_address: str,
                 economics: TokenEconomics = None,
                 *args, **kwargs
                 ) -> None:

        super().__init__(deployer_address=deployer_address, *args, **kwargs)
        self._creator = deployer_address
        if not economics:
            economics = TokenEconomics()
        self.__economics = economics

    def deploy(self, gas_limit: int = None) -> dict:
        """
        Deploy and publish the NuCypher Token contract
        to the blockchain network specified in self.blockchain.network.

        Deployment can only ever be executed exactly once!
        """
        self.check_deployment_readiness()

        _contract, deployment_txhash = self.blockchain.deploy_contract(
                                       self.contract_name,
                                       self.__economics.erc20_total_supply)

        self._contract = _contract
        return {'txhash': deployment_txhash}


class DispatcherDeployer(ContractDeployer):
    """
    Ethereum smart contract that acts as a proxy to another ethereum contract,
    used as a means of "dispatching" the correct version of the contract to the client
    """

    contract_name = 'Dispatcher'
    _upgradeable = False

    DISPATCHER_SECRET_LENGTH = 32

    def __init__(self, target_contract: Contract, bare: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_contract = target_contract
        if bare:
            self._contract = self.blockchain.get_proxy(target_address=self.target_contract.address,
                                                                 proxy_name=self.contract_name)

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> dict:
        args = (self.contract_name, self.target_contract.address, secret_hash)
        dispatcher_contract, txhash = self.blockchain.deploy_contract(gas_limit=gas_limit, *args)
        self._contract = dispatcher_contract
        return {'txhash': txhash}

    def retarget(self, new_target: str, existing_secret_plaintext: bytes, new_secret_hash: bytes) -> bytes:
        if new_target == self.target_contract.address:
            raise self.ContractDeploymentError(f"{new_target} is already targeted by {self.contract_name}: {self._contract.address}")
        if new_target == self._contract.address:
            raise self.ContractDeploymentError(f"{self.contract_name} {self._contract.address} cannot target itself.")

        origin_args = {'from': self.deployer_address, 'gasPrice': self.blockchain.w3.eth.gasPrice}  # TODO: Gas management
        txhash = self._contract.functions.upgrade(new_target, existing_secret_plaintext, new_secret_hash).transact(origin_args)
        _receipt = self.blockchain.wait_for_receipt(txhash=txhash)
        return txhash

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes) -> bytes:
        origin_args = {'from': self.deployer_address, 'gasPrice': self.blockchain.w3.eth.gasPrice}  # TODO: Gas management
        txhash = self._contract.functions.rollback(existing_secret_plaintext, new_secret_hash).transact(origin_args)
        _receipt = self.blockchain.wait_for_receipt(txhash=txhash)
        return txhash


class StakingEscrowDeployer(ContractDeployer):
    """
    Deploys the StakingEscrow ethereum contract to the blockchain.  Depends on NucypherTokenAgent
    """

    agency = StakingEscrowAgent
    contract_name = agency.registry_contract_name
    _upgradeable = True
    __proxy_deployer = DispatcherDeployer

    def __init__(self,  economics: TokenEconomics = None, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        if not economics:
            economics = TokenEconomics()
        self.__economics = economics

    def __check_policy_manager(self):
        result = self.contract.functions.policyManager().call()
        if result is self.blockchain.NULL_ADDRESS:
            raise RuntimeError("PolicyManager contract is not initialized.")

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> dict:
        """
        Deploy and publish the StakingEscrow contract
        to the blockchain network specified in self.blockchain.network.

        Deployment can only ever be executed exactly once!

        Emits the following blockchain network transactions:
            - StakingEscrow contract deployment
            - StakingEscrow dispatcher deployment
            - Transfer reward tokens origin -> StakingEscrow contract
            - StakingEscrow contract initialization

        Returns transaction hashes in a dict.
        """

        # Raise if not all-systems-go
        self.check_deployment_readiness()

        # Build deployment arguments
        origin_args = {'from': self.deployer_address,
                       'gasPrice': self.blockchain.w3.eth.gasPrice}
        if gas_limit:
            origin_args.update({'gas': gas_limit})

        # 1 - Deploy #
        the_escrow_contract, deploy_txhash, = \
            self.blockchain.deploy_contract(self.contract_name,
                                                      self.token_agent.contract_address,
                                                      *self.__economics.staking_deployment_parameters)

        # 2 - Deploy the dispatcher used for updating this contract #
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=the_escrow_contract,
                                                 deployer_address=self.deployer_address)

        dispatcher_deploy_txhashes = dispatcher_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer.contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract
        wrapped_escrow_contract = self.blockchain._wrap_contract(dispatcher_contract,
                                                                           target_contract=the_escrow_contract)

        # Switch the contract for the wrapped one
        the_escrow_contract = wrapped_escrow_contract

        # 3 - Transfer tokens to the staker escrow #
        reward_txhash = self.token_agent.contract.functions.transfer(
            the_escrow_contract.address,
            self.__economics.erc20_reward_supply
        ).transact(origin_args)

        _reward_receipt = self.blockchain.wait_for_receipt(reward_txhash)
        escrow_balance = self.token_agent.get_balance(address=the_escrow_contract.address)

        # 4 - Initialize the Staker Escrow contract
        init_txhash = the_escrow_contract.functions.initialize().transact(origin_args)
        _init_receipt = self.blockchain.wait_for_receipt(init_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deploy': deploy_txhash,
                                   'dispatcher_deploy': dispatcher_deploy_txhashes['txhash'],
                                   'reward_transfer': reward_txhash,
                                   'initialize': init_txhash}

        # Set the contract and transaction hashes #
        self._contract = the_escrow_contract
        self.deployment_transactions = deployment_transactions
        return deployment_transactions

    def upgrade(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):

        # Raise if not all-systems-go
        self.check_deployment_readiness()
        origin_args = {'from': self.deployer_address, 'gas': 5000000}  # TODO: Gas management

        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                                proxy_name=self.__proxy_deployer.contract_name,
                                                                                use_proxy_address=False)
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=existing_bare_contract,
                                                 deployer_address=self.deployer_address,
                                                 bare=True)  # acquire agency for the dispatcher itself.

        # 2 - Deploy new version #
        the_escrow_contract, deploy_txhash = self.blockchain.deploy_contract(self.contract_name,
                                                                                       self.token_agent.contract_address,
                                                                                       *self.__economics.staking_deployment_parameters)

        # 5 - Wrap the escrow contract
        wrapped_escrow_contract = self.blockchain._wrap_contract(wrapper_contract=dispatcher_deployer.contract,
                                                                           target_contract=the_escrow_contract)
        self._contract = wrapped_escrow_contract

        # 4 - Set the new Dispatcher target
        upgrade_tx_hash = dispatcher_deployer.retarget(new_target=the_escrow_contract.address,
                                                       existing_secret_plaintext=existing_secret_plaintext,
                                                       new_secret_hash=new_secret_hash)
        _upgrade_receipt = self.blockchain.wait_for_receipt(upgrade_tx_hash)

        # Respond
        upgrade_transaction = {'deploy': deploy_txhash, 'retarget': upgrade_tx_hash}
        return upgrade_transaction

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):
        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                      proxy_name=self.__proxy_deployer.contract_name,
                                                                      use_proxy_address=False)
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=existing_bare_contract,
                                                 deployer_address=self.deployer_address,
                                                 bare=True)  # acquire agency for the dispatcher itself.

        rollback_txhash = dispatcher_deployer.rollback(existing_secret_plaintext=existing_secret_plaintext,
                                                       new_secret_hash=new_secret_hash)

        _rollback_receipt = self.blockchain.wait_for_receipt(txhash=rollback_txhash)
        return rollback_txhash

    def make_agent(self) -> EthereumContractAgent:
        self.__check_policy_manager()  # Ensure the PolicyManager contract has already been initialized
        agent = self.agency(blockchain=self.blockchain, contract=self._contract)
        return agent


class PolicyManagerDeployer(ContractDeployer):
    """
    Depends on StakingEscrow and NucypherTokenAgent
    """

    agency = PolicyAgent
    contract_name = agency.registry_contract_name
    _upgradeable = True
    __proxy_deployer = DispatcherDeployer

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(blockchain=self.blockchain, contract=self._contract)
        return agent

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> Dict[str, str]:
        self.check_deployment_readiness()

        # Creator deploys the policy manager
        policy_manager_contract, deploy_txhash = self.blockchain.deploy_contract(self.contract_name, self.staking_agent.contract_address)

        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               target_contract=policy_manager_contract,
                                               deployer_address=self.deployer_address)

        proxy_deploy_txhashes = proxy_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)

        # Cache the dispatcher contract
        proxy_contract = proxy_deployer.contract
        self.__proxy_contract = proxy_contract

        # Wrap the escrow contract
        wrapped = self.blockchain._wrap_contract(proxy_contract, target_contract=policy_manager_contract)

        # Switch the contract for the wrapped one
        policy_manager_contract = wrapped

        # Configure the StakingEscrow contract by setting the PolicyManager
        tx_args = {'from': self.deployer_address}
        if gas_limit:
            tx_args.update({'gas': gas_limit})
        policy_setter_txhash = self.staking_agent.contract.functions.setPolicyManager(policy_manager_contract.address).transact(tx_args)

        self.blockchain.wait_for_receipt(policy_setter_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deployment': deploy_txhash,
                                   'dispatcher_deployment': proxy_deploy_txhashes['txhash'],
                                   'set_policy_manager': policy_setter_txhash}

        self.deployment_transactions = deployment_transactions
        self._contract = policy_manager_contract

        return deployment_transactions

    def upgrade(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):

        self.check_deployment_readiness()

        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                                proxy_name=self.__proxy_deployer.contract_name,
                                                                                use_proxy_address=False)

        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               target_contract=existing_bare_contract,
                                               deployer_address=self.deployer_address,
                                               bare=True)  # acquire agency for the dispatcher itself.

        # Creator deploys the policy manager
        policy_manager_contract, deploy_txhash = self.blockchain.deploy_contract(self.contract_name,
                                                                                           self.staking_agent.contract_address)

        upgrade_tx_hash = proxy_deployer.retarget(new_target=policy_manager_contract.address,
                                                  existing_secret_plaintext=existing_secret_plaintext,
                                                  new_secret_hash=new_secret_hash)
        _upgrade_receipt = self.blockchain.wait_for_receipt(upgrade_tx_hash)

        # Wrap the escrow contract
        wrapped_policy_manager_contract = self.blockchain._wrap_contract(proxy_deployer.contract,
                                                                                   target_contract=policy_manager_contract)

        # Switch the contract for the wrapped one
        policy_manager_contract = wrapped_policy_manager_contract

        self._contract = policy_manager_contract

        upgrade_transaction = {'deploy': deploy_txhash,
                               'retarget': upgrade_tx_hash}

        return upgrade_transaction

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):
        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                                proxy_name=self.__proxy_deployer.contract_name,
                                                                                use_proxy_address=False)
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=existing_bare_contract,
                                                 deployer_address=self.deployer_address,
                                                 bare=True)  # acquire agency for the dispatcher itself.

        rollback_txhash = dispatcher_deployer.rollback(existing_secret_plaintext=existing_secret_plaintext,
                                                       new_secret_hash=new_secret_hash)

        _rollback_receipt = self.blockchain.wait_for_receipt(txhash=rollback_txhash)
        return rollback_txhash


class LibraryLinkerDeployer(ContractDeployer):

    contract_name = 'UserEscrowLibraryLinker'

    def __init__(self, target_contract: Contract, bare: bool = False, *args, **kwargs):
        self.target_contract = target_contract
        super().__init__(*args, **kwargs)
        if bare:
            self._contract = self.blockchain.get_proxy(target_address=self.target_contract.address,
                                                                 proxy_name=self.contract_name)

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> dict:
        linker_args = (self.contract_name, self.target_contract.address, secret_hash)
        linker_contract, linker_deployment_txhash = self.blockchain.deploy_contract(gas_limit=gas_limit, *linker_args)
        self._contract = linker_contract
        return {'txhash': linker_deployment_txhash}

    def retarget(self, new_target: str, existing_secret_plaintext: bytes, new_secret_hash: bytes):
        if new_target == self.target_contract.address:
            raise self.ContractDeploymentError(f"{new_target} is already targeted by {self.contract_name}: {self._contract.address}")
        if new_target == self._contract.address:
            raise self.ContractDeploymentError(f"{self.contract_name} {self._contract.address} cannot target itself.")

        origin_args = {'from': self.deployer_address}  # TODO: Gas management
        txhash = self._contract.functions.upgrade(new_target, existing_secret_plaintext, new_secret_hash).transact(origin_args)
        _receipt = self.blockchain.wait_for_receipt(txhash=txhash)
        return txhash


class UserEscrowProxyDeployer(ContractDeployer):

    contract_name = 'UserEscrowProxy'
    __proxy_deployer = LibraryLinkerDeployer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)

    def __get_state_contract(self) -> str:
        return self.contract.functions.getStateContract()

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> dict:

        deployment_transactions = dict()

        # Proxy
        proxy_args = (self.contract_name,
                      self.token_agent.contract_address,
                      self.staking_agent.contract_address,
                      self.policy_agent.contract_address)
        user_escrow_proxy_contract, proxy_deployment_txhash = self.blockchain.deploy_contract(gas_limit=gas_limit, *proxy_args)
        self._contract = user_escrow_proxy_contract
        deployment_transactions['deployment_txhash'] = proxy_deployment_txhash

        # Proxy-Proxy
        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               deployer_address=self.deployer_address,
                                               target_contract=user_escrow_proxy_contract)

        proxy_deployment_txhashes = proxy_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)

        deployment_transactions['proxy_deployment'] = proxy_deployment_txhash
        return deployment_transactions

    @classmethod
    def get_latest_version(cls, blockchain) -> Contract:
        contract = blockchain.get_contract_by_name(name=cls.contract_name, proxy_name=cls.__proxy_deployer.contract_name)
        return contract

    def upgrade(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):

        deployment_transactions = dict()

        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                      proxy_name=self.__proxy_deployer.contract_name,
                                                                      use_proxy_address=False)
        # Proxy-Proxy
        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               deployer_address=self.deployer_address,
                                               target_contract=existing_bare_contract,
                                               bare=True)

        # Proxy
        proxy_args = (self.contract_name,
                      self.token_agent.contract_address,
                      self.staking_agent.contract_address,
                      self.policy_agent.contract_address)

        user_escrow_proxy_contract, proxy_deployment_txhash = self.blockchain.deploy_contract(*proxy_args)
        self._contract = user_escrow_proxy_contract
        deployment_transactions['deployment_txhash'] = proxy_deployment_txhash

        proxy_deployer.retarget(new_target=user_escrow_proxy_contract.address,
                                existing_secret_plaintext=existing_secret_plaintext,
                                new_secret_hash=new_secret_hash)

        deployment_transactions['proxy_deployment'] = proxy_deployment_txhash

        return deployment_transactions

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):
        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                      proxy_name=self.__proxy_deployer.contract_name,
                                                                      use_proxy_address=False)

        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=existing_bare_contract,
                                                 deployer_address=self.deployer_address,
                                                 bare=True)  # acquire agency for the dispatcher itself.

        rollback_txhash = dispatcher_deployer.rollback(existing_secret_plaintext=existing_secret_plaintext,
                                                       new_secret_hash=new_secret_hash)

        _rollback_receipt = self.blockchain.wait_for_receipt(txhash=rollback_txhash)
        return rollback_txhash


class UserEscrowDeployer(ContractDeployer):

    agency = UserEscrowAgent
    contract_name = agency.registry_contract_name
    _upgradeable = True
    __linker_deployer = LibraryLinkerDeployer
    __allocation_registry = AllocationRegistry

    def __init__(self, allocation_registry: AllocationRegistry = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        self.policy_agent = PolicyAgent(blockchain=self.blockchain)
        self.__beneficiary_address = NO_BENEFICIARY
        self.__allocation_registry = allocation_registry or self.__allocation_registry()

    def make_agent(self) -> EthereumContractAgent:
        if self.__beneficiary_address is NO_BENEFICIARY:
            raise self.ContractDeploymentError("No beneficiary assigned to {}".format(self.contract.address))
        agent = self.agency(blockchain=self.blockchain,
                            beneficiary=self.__beneficiary_address,
                            allocation_registry=self.__allocation_registry)
        return agent

    @property
    def allocation_registry(self):
        return self.__allocation_registry

    def assign_beneficiary(self, beneficiary_address: str) -> str:
        """Relinquish ownership of a UserEscrow deployment to the beneficiary"""
        if not is_checksum_address(beneficiary_address):
            raise self.ContractDeploymentError("{} is not a valid checksum address.".format(beneficiary_address))
        txhash = self.contract.functions.transferOwnership(beneficiary_address).transact({'from': self.deployer_address,
                                                                                          'gas': 500_000,
                                                                                          'gasPrice': self.blockchain.w3.eth.gasPrice})  # TODO: Gas
        self.blockchain.wait_for_receipt(txhash)
        self.__beneficiary_address = beneficiary_address
        return txhash

    def initial_deposit(self, value: int, duration: int) -> dict:
        """Allocate an amount of tokens with lock time, and transfer ownership to the beneficiary"""
        # Approve
        allocation_receipts = dict()
        approve_receipt = self.token_agent.approve_transfer(amount=value,
                                                            target_address=self.contract.address,
                                                            sender_address=self.deployer_address)
        allocation_receipts['approve'] = approve_receipt

        # Deposit
        try:
            # TODO: Gas management
            args = {'from': self.deployer_address,
                    'gasPrice': self.blockchain.w3.eth.gasPrice,
                    'gas': 200_000}
            deposit_receipt = self.contract.functions.initialDeposit(value, duration).transact(args)
        except TransactionFailed:
            raise  # TODO

        # TODO: Do something with allocation_receipts. Perhaps it should be returned instead of only the last receipt.
        allocation_receipts['initial_deposit'] = deposit_receipt
        return deposit_receipt

    def enroll_principal_contract(self):
        if self.__beneficiary_address is NO_BENEFICIARY:
            raise self.ContractDeploymentError("No beneficiary assigned to {}".format(self.contract.address))
        self.__allocation_registry.enroll(beneficiary_address=self.__beneficiary_address,
                                          contract_address=self.contract.address,
                                          contract_abi=self.contract.abi)

    def deliver(self, value: int, duration: int, beneficiary_address: str) -> dict:
        """
        Transfer allocated tokens and hand-off the contract to the beneficiary.

         Encapsulates three operations:
            - Initial Deposit
            - Transfer Ownership
            - Enroll in Allocation Registry

        """

        deposit_txhash = self.initial_deposit(value=value, duration=duration)
        assign_txhash = self.assign_beneficiary(beneficiary_address=beneficiary_address)
        self.enroll_principal_contract()
        return dict(deposit_txhash=deposit_txhash, assign_txhash=assign_txhash)

    def deploy(self, gas_limit: int = None) -> dict:
        """Deploy a new instance of UserEscrow to the blockchain."""

        self.check_deployment_readiness()

        deployment_transactions = dict()
        linker_contract = self.blockchain.get_contract_by_name(name=self.__linker_deployer.contract_name)
        args = (self.contract_name, linker_contract.address, self.token_agent.contract_address)
        user_escrow_contract, deploy_txhash = self.blockchain.deploy_contract(*args, gas_limit=gas_limit, enroll=False)
        deployment_transactions['deploy_user_escrow'] = deploy_txhash

        self._contract = user_escrow_contract
        return deployment_transactions


class AdjudicatorDeployer(ContractDeployer):

    agency = AdjudicatorAgent
    contract_name = agency.registry_contract_name
    _upgradeable = True
    __proxy_deployer = DispatcherDeployer

    def __init__(self, economics: SlashingEconomics = None, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)
        self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        if not economics:
            economics = SlashingEconomics()
        self.__economics = economics

    def deploy(self, secret_hash: bytes, gas_limit: int = None) -> Dict[str, str]:
        self.check_deployment_readiness()

        adjudicator_contract, deploy_txhash = self.blockchain.deploy_contract(self.contract_name,
                                                                              self.staking_agent.contract_address,
                                                                              *self.__economics.deployment_parameters,
                                                                              gas_limit=gas_limit)

        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               target_contract=adjudicator_contract,
                                               deployer_address=self.deployer_address)

        proxy_deploy_txhashes = proxy_deployer.deploy(secret_hash=secret_hash)

        # Cache the dispatcher contract
        proxy_contract = proxy_deployer.contract
        self.__proxy_contract = proxy_contract

        # Wrap the escrow contract
        wrapped = self.blockchain._wrap_contract(proxy_contract, target_contract=adjudicator_contract)

        # Switch the contract for the wrapped one
        adjudicator_contract = wrapped

        # Gather the transaction hashes
        deployment_transactions = {'deployment': deploy_txhash,
                                   'dispatcher_deployment': proxy_deploy_txhashes['txhash']}

        self.deployment_transactions = deployment_transactions
        self._contract = adjudicator_contract

        return deployment_transactions

    def upgrade(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):

        self.check_deployment_readiness()

        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                      proxy_name=self.__proxy_deployer.contract_name,
                                                                      use_proxy_address=False)

        proxy_deployer = self.__proxy_deployer(blockchain=self.blockchain,
                                               target_contract=existing_bare_contract,
                                               deployer_address=self.deployer_address,
                                               bare=True)

        adjudicator_contract, deploy_txhash = self.blockchain.deploy_contract(self.contract_name,
                                                                              self.staking_agent.contract_address,
                                                                              *self.__economics.deployment_parameters)

        upgrade_tx_hash = proxy_deployer.retarget(new_target=adjudicator_contract.address,
                                                  existing_secret_plaintext=existing_secret_plaintext,
                                                  new_secret_hash=new_secret_hash)
        _upgrade_receipt = self.blockchain.wait_for_receipt(upgrade_tx_hash)

        # Wrap the escrow contract
        wrapped_adjudicator_contract = self.blockchain._wrap_contract(proxy_deployer.contract, target_contract=adjudicator_contract)

        # Switch the contract for the wrapped one
        policy_manager_contract = wrapped_adjudicator_contract

        self._contract = policy_manager_contract

        upgrade_transaction = {'deploy': deploy_txhash, 'retarget': upgrade_tx_hash}
        return upgrade_transaction

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes):
        existing_bare_contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                                      proxy_name=self.__proxy_deployer.contract_name,
                                                                      use_proxy_address=False)
        dispatcher_deployer = DispatcherDeployer(blockchain=self.blockchain,
                                                 target_contract=existing_bare_contract,
                                                 deployer_address=self.deployer_address,
                                                 bare=True)  # acquire agency for the dispatcher itself.

        rollback_txhash = dispatcher_deployer.rollback(existing_secret_plaintext=existing_secret_plaintext,
                                                       new_secret_hash=new_secret_hash)

        _rollback_receipt = self.blockchain.wait_for_receipt(txhash=rollback_txhash)
        return rollback_txhash
