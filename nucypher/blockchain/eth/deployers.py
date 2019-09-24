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


from typing import Tuple, Dict

from constant_sorrow.constants import CONTRACT_NOT_DEPLOYED, NO_DEPLOYER_CONFIGURED, NO_BENEFICIARY
from eth_utils import is_checksum_address
from web3.contract import Contract

from nucypher.blockchain.economics import StandardTokenEconomics
from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.agents import (
    EthereumContractAgent,
    StakingEscrowAgent,
    NucypherTokenAgent,
    PolicyManagerAgent,
    UserEscrowAgent,
    AdjudicatorAgent
)
from nucypher.blockchain.eth.constants import DISPATCHER_CONTRACT_NAME
from nucypher.blockchain.eth.decorators import validate_secret
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import AllocationRegistry, BaseContractRegistry


class BaseContractDeployer:

    _interface_class = BlockchainDeployerInterface

    agency = NotImplemented
    contract_name = NotImplemented
    deployment_steps = NotImplemented
    upgrade_steps = NotImplemented
    rollback_steps = NotImplemented

    _upgradeable = NotImplemented
    _ownable = NotImplemented
    _proxy_deployer = NotImplemented

    class ContractDeploymentError(Exception):
        pass

    class ContractNotDeployed(ContractDeploymentError):
        pass

    def __init__(self,
                 registry: BaseContractRegistry,
                 economics: TokenEconomics = None,
                 deployer_address: str = None):

        #
        # Validate
        #
        self.blockchain = BlockchainInterfaceFactory.get_interface()
        if not isinstance(self.blockchain, BlockchainDeployerInterface):
            raise ValueError("No deployer interface connection available.")

        #
        # Defaults
        #
        self.registry = registry
        self.deployment_receipts = dict()
        self._contract = CONTRACT_NOT_DEPLOYED
        self.__proxy_contract = NotImplemented
        self.__deployer_address = deployer_address
        self.__ready_to_deploy = False
        self.__economics = economics or StandardTokenEconomics()

    @property
    def economics(self) -> TokenEconomics:
        """Read-only access for economics instance."""
        return self.__economics

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
        for rule_is_satisfied, failure_reason in rules:
            if not rule_is_satisfied:                        # If this rule fails...
                if fail is True:
                    raise self.ContractDeploymentError(failure_reason)
                else:
                    disqualifications.append(failure_reason)   # ... here's why

        is_ready = len(disqualifications) == 0
        return is_ready, disqualifications

    def _ensure_contract_deployment(self) -> bool:
        """Raises ContractDeploymentError if the contract has not been deployed."""

        if self._contract is CONTRACT_NOT_DEPLOYED:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed.'.format(class_name)
            raise self.ContractDeploymentError(message)
        return True

    def deploy(self, gas_limit: int, progress) -> dict:
        """
        Provides for the setup, deployment, and initialization of ethereum smart contracts.
        Emits the configured blockchain network transactions for single contract instance publication.
        """
        raise NotImplementedError

    def make_agent(self) -> EthereumContractAgent:
        agent = self.agency(registry=self.registry, contract=self._contract)
        return agent

    def get_latest_enrollment(self, registry: BaseContractRegistry) -> Contract:
        """Get the latest enrolled version of the contract from the registry."""
        contract = self.blockchain.get_contract_by_name(name=self.contract_name,
                                                        registry=registry,
                                                        use_proxy_address=False,
                                                        version='latest')
        return contract


class OwnableContractMixin:

    _ownable = True

    class ContractNotOwnable(RuntimeError):
        pass

    def transfer_ownership(self, new_owner: str, transaction_gas_limit: int = None):
        if not self._ownable:
            raise self.ContractNotOwnable(f"{self.contract_name} is not ownable.")

        receipts = dict()
        if self._upgradeable:

            #
            # Upgrade Proxy
            #

            existing_bare_contract = self.get_principal_contract(registry=self.registry,
                                                                 provider_uri=self.blockchain.provider_uri)

            proxy_deployer = self.get_proxy_deployer(registry=self.registry)
            proxy_contract_function = proxy_deployer.contract.functions.transferOwnership(new_owner)
            proxy_receipt = self.blockchain.send_transaction(sender_address=self.deployer_address,
                                                             contract_function=proxy_contract_function,
                                                             transaction_gas_limit=transaction_gas_limit)

            receipts['proxy'] = proxy_receipt

        #
        # Upgrade Principal
        #

        contract_function = existing_bare_contract.functions.transferOwnership(new_owner)
        principal_receipt = self.blockchain.send_transaction(sender_address=self.deployer_address,
                                                             contract_function=contract_function,
                                                             transaction_gas_limit=transaction_gas_limit)
        receipts['principal'] = principal_receipt
        return receipts


class UpgradeableContractMixin:

    _upgradeable = True
    _proxy_deployer = NotImplemented

    class ContractNotUpgradeable(RuntimeError):
        pass
    
    def deploy(self, secret_hash: bytes, initial_deployment: bool = True, gas_limit: int = None, progress = None) -> dict:
        """
        Provides for the setup, deployment, and initialization of ethereum smart contracts.
        Emits the configured blockchain network transactions for single contract instance publication.
        """
        if not self._upgradeable:
            raise self.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")
        raise NotImplementedError

    def get_principal_contract(self, registry: BaseContractRegistry, provider_uri: str = None) -> Contract:
        """
        Get the on-chain targeted version of the principal contract directly
        without assembling it with its proxy.
        """
        if not self._upgradeable:
            raise self.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        principal_contract = blockchain.get_contract_by_name(name=self.contract_name,
                                                             registry=registry,
                                                             proxy_name=self._proxy_deployer.contract_name,
                                                             use_proxy_address=False)
        return principal_contract

    def get_proxy_contract(self, registry: BaseContractRegistry, provider_uri: str = None) -> Contract:
        if not self._upgradeable:
            raise cls.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        principal_contract = self.get_principal_contract(registry=registry, provider_uri=provider_uri)
        proxy_contract = blockchain.get_proxy_contract(registry=registry,
                                                       target_address=principal_contract.address,
                                                       proxy_name=self._proxy_deployer.contract_name)
        return proxy_contract

    def get_proxy_deployer(self,
                           registry: BaseContractRegistry,
                           provider_uri: str = None
                           ) -> BaseContractDeployer:
        principal_contract = self.get_principal_contract(registry=registry, provider_uri=provider_uri)
        proxy_deployer = self._proxy_deployer(registry=registry,
                                              deployer_address=self.deployer_address,
                                              target_contract=principal_contract,
                                              bare=True)  # acquire access to the proxy itself.
        return proxy_deployer

    def retarget(self,
                 target_address: str,
                 existing_secret_plaintext: bytes,
                 new_secret_hash: bytes,
                 gas_limit: int = None):
        """
        Directly engage a proxy contract for an existing deployment, executing the proxy's
        upgrade interfaces to verify upgradeability and modify the on-chain contract target.
        """

        if not self._upgradeable:
            raise self.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")

        # 1 - Get Bare Contracts
        existing_bare_contract = self.get_principal_contract(registry=self.registry, provider_uri=self.blockchain.provider_uri)
        proxy_deployer = self.get_proxy_deployer(registry=self.registry, provider_uri=self.blockchain.provider_uri)

        # 2 - Retarget
        receipt = proxy_deployer.retarget(new_target=target_address,
                                          existing_secret_plaintext=existing_secret_plaintext,
                                          new_secret_hash=new_secret_hash,
                                          gas_limit=gas_limit)
        return receipt

    def upgrade(self, existing_secret_plaintext: bytes, new_secret_hash: bytes, gas_limit: int = None):
        """
        Deploy a new version of a contract, then engage the proxy contract's upgrade interfaces.
        """

        # 1 - Raise if not all-systems-go #
        if not self._upgradeable:
            raise self.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")
        # TODO: Fails when this same object was used previously to deploy
        self.check_deployment_readiness()

        # 2 - Get Bare Contracts
        existing_bare_contract = self.get_principal_contract(registry=self.registry, provider_uri=self.blockchain.provider_uri)
        proxy_deployer = self.get_proxy_deployer(registry=self.registry, provider_uri=self.blockchain.provider_uri)

        # 3 - Deploy new version
        new_contract, deploy_receipt = self._deploy_essential(gas_limit=gas_limit)

        # 4 - Wrap the escrow contract
        wrapped_contract = self.blockchain._wrap_contract(wrapper_contract=proxy_deployer.contract,
                                                          target_contract=new_contract)

        # 5 - Set the new Dispatcher target
        upgrade_receipt = proxy_deployer.retarget(new_target=new_contract.address,
                                                  existing_secret_plaintext=existing_secret_plaintext,
                                                  new_secret_hash=new_secret_hash,
                                                  gas_limit=gas_limit)

        # 6 - Respond
        upgrade_transaction = {'deploy': deploy_receipt, 'retarget': upgrade_receipt}
        self._contract = wrapped_contract  # Switch the contract for the wrapped one
        return upgrade_transaction

    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes, gas_limit: int = None):
        """
        Execute an existing deployment's proxy contract, engaging the upgrade rollback interfaces,
        modifying the proxy's on-chain contract target to the most recent previous target.
        """

        if not self._upgradeable:
            raise self.ContractNotUpgradeable(f"{self.contract_name} is not upgradeable.")

        existing_bare_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                      name=self.contract_name,
                                                                      proxy_name=self._proxy_deployer.contract_name,
                                                                      use_proxy_address=False)
        proxy_deployer = self.get_proxy_deployer(registry=self.registry, provider_uri=self.blockchain.provider_uri)
        rollback_receipt = proxy_deployer.rollback(existing_secret_plaintext=existing_secret_plaintext,
                                                   new_secret_hash=new_secret_hash,
                                                   gas_limit=gas_limit)

        return rollback_receipt

    def _finish_bare_deployment(self, deployment_receipt: dict, progress = None) -> dict:
        """Used to divert flow control for bare contract deployments."""
        deployment_step_name = self.deployment_steps[0]
        result = {deployment_step_name: deployment_receipt}
        self.deployment_receipts.update(result)
        if progress:
            progress.update(len(self.deployment_steps))  # Update the progress bar to completion.
        return result


class NucypherTokenDeployer(BaseContractDeployer):

    agency = NucypherTokenAgent
    contract_name = agency.registry_contract_name
    deployment_steps = ('contract_deployment', )
    _upgradeable = False
    _ownable = False

    def deploy(self, gas_limit: int = None, progress=None) -> dict:
        """
        Deploy and publish the NuCypher Token contract
        to the blockchain network specified in self.blockchain.network.

        Deployment can only ever be executed exactly once!
        """
        self.check_deployment_readiness()

        # Order-sensitive!
        contract, deployment_receipt = self.blockchain.deploy_contract(self.deployer_address,
                                                                       self.registry,
                                                                       self.contract_name,
                                                                       gas_limit=gas_limit,
                                                                       _totalSupply=self.economics.erc20_total_supply)
        if progress:
            progress.update(1)
        self._contract = contract
        return {self.deployment_steps[0]: deployment_receipt}


class DispatcherDeployer(BaseContractDeployer, OwnableContractMixin):
    """
    Ethereum smart contract that acts as a proxy to another ethereum contract,
    used as a means of "dispatching" the correct version of the contract to the client
    """

    contract_name = DISPATCHER_CONTRACT_NAME
    deployment_steps = ('contract_deployment', )
    _upgradeable = False
    _secret_length = 32

    def __init__(self, target_contract: Contract, bare: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_contract = target_contract
        if bare:
            self._contract = self.blockchain.get_proxy_contract(target_address=self.target_contract.address,
                                                                proxy_name=self.contract_name,
                                                                registry=self.registry)

    def deploy(self, secret_hash: bytes, gas_limit: int = None, progress=None) -> dict:
        args = (self.deployer_address,
                self.registry,
                self.contract_name,
                self.target_contract.address,
                bytes(secret_hash))   # Tux's favorite.

        dispatcher_contract, receipt = self.blockchain.deploy_contract(gas_limit=gas_limit, *args)
        if progress:
            progress.update(1)

        self._contract = dispatcher_contract
        self.deployment_receipts.update({'deployment': receipt})
        return {self.deployment_steps[0]: receipt}

    @validate_secret
    def retarget(self, new_target: str, existing_secret_plaintext: bytes, new_secret_hash: bytes, gas_limit: int = None) -> dict:
        if new_target == self.target_contract.address:
            raise self.ContractDeploymentError(f"{new_target} is already targeted by {self.contract_name}: {self._contract.address}")
        if new_target == self._contract.address:
            raise self.ContractDeploymentError(f"{self.contract_name} {self._contract.address} cannot target itself.")

        upgrade_function = self._contract.functions.upgrade(new_target, existing_secret_plaintext, new_secret_hash)
        upgrade_receipt = self.blockchain.send_transaction(contract_function=upgrade_function,
                                                           sender_address=self.deployer_address,
                                                           transaction_gas_limit=gas_limit)
        return upgrade_receipt

    @validate_secret
    def rollback(self, existing_secret_plaintext: bytes, new_secret_hash: bytes, gas_limit: int = None) -> dict:
        origin_args = {}  # TODO: Gas management
        if gas_limit:
            origin_args.update({'gas': gas_limit})

        rollback_function = self._contract.functions.rollback(existing_secret_plaintext, new_secret_hash)
        rollback_receipt = self.blockchain.send_transaction(contract_function=rollback_function,
                                                            sender_address=self.deployer_address,
                                                            payload=origin_args)
        return rollback_receipt


class StakingEscrowDeployer(BaseContractDeployer, UpgradeableContractMixin, OwnableContractMixin):
    """
    Deploys the StakingEscrow ethereum contract to the blockchain.  Depends on NucypherTokenAgent
    """

    agency = StakingEscrowAgent
    contract_name = agency.registry_contract_name
    deployment_steps = ('contract_deployment', 'dispatcher_deployment', 'reward_transfer', 'initialize')
    _proxy_deployer = DispatcherDeployer

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dispatcher_contract = None

        token_contract_name = NucypherTokenDeployer.contract_name
        self.token_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                   name=token_contract_name)

    def __check_policy_manager(self):
        result = self.contract.functions.policyManager().call()
        if result == self.blockchain.NULL_ADDRESS:
            raise RuntimeError("PolicyManager contract is not initialized.")

    def _deploy_essential(self, gas_limit: int = None):
        escrow_constructor_args = (self.token_contract.address, *self.economics.staking_deployment_parameters)
        the_escrow_contract, deploy_receipt = self.blockchain.deploy_contract(
            self.deployer_address,
            self.registry,
            self.contract_name,
            gas_limit=gas_limit,
            *escrow_constructor_args,
        )

        return the_escrow_contract, deploy_receipt

    def deploy(self,
               initial_deployment: bool = True,
               secret_hash: bytes = None,
               gas_limit: int = None,
               progress=None
               ) -> dict:
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

        if initial_deployment and not secret_hash:
            raise ValueError(f"An upgrade secret hash is required to perform an initial"
                             f" deployment series for {self.contract_name}.")

        # Raise if not all-systems-go
        self.check_deployment_readiness()

        # Build deployment arguments
        origin_args = {}
        if gas_limit:
            origin_args.update({'gas': gas_limit})

        # 1 - Deploy #
        the_escrow_contract, deploy_receipt = self._deploy_essential(gas_limit=gas_limit)

        # This is the end of bare deployment.
        if not initial_deployment:
            self._contract = the_escrow_contract
            return self._finish_bare_deployment(deployment_receipt=deploy_receipt,
                                                progress=progress)

        if progress:
            progress.update(1)

        # 2 - Deploy the dispatcher used for updating this contract #
        dispatcher_deployer = DispatcherDeployer(registry=self.registry,
                                                 target_contract=the_escrow_contract,
                                                 deployer_address=self.deployer_address)

        dispatcher_receipts = dispatcher_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)
        dispatcher_deploy_receipt = dispatcher_receipts[dispatcher_deployer.deployment_steps[0]]
        if progress:
            progress.update(1)

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer.contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract
        wrapped_escrow_contract = self.blockchain._wrap_contract(dispatcher_contract,
                                                                 target_contract=the_escrow_contract)

        # Switch the contract for the wrapped one
        the_escrow_contract = wrapped_escrow_contract

        # 3 - Transfer the reward supply tokens to StakingEscrow #
        reward_function = self.token_contract.functions.transfer(the_escrow_contract.address,
                                                                 self.economics.erc20_reward_supply)

        # TODO: Confirmations / Successful Transaction Indicator / Events ??
        reward_receipt = self.blockchain.send_transaction(contract_function=reward_function,
                                                          sender_address=self.deployer_address,
                                                          payload=origin_args)
        if progress:
            progress.update(1)

        # 4 - Initialize the StakingEscrow contract
        init_function = the_escrow_contract.functions.initialize()

        init_receipt = self.blockchain.send_transaction(contract_function=init_function,
                                                        sender_address=self.deployer_address,
                                                        payload=origin_args)
        if progress:
            progress.update(1)

        # Gather the transaction receipts
        ordered_receipts = (deploy_receipt, dispatcher_deploy_receipt, reward_receipt, init_receipt)
        deployment_receipts = dict(zip(self.deployment_steps, ordered_receipts))

        # Set the contract and transaction receipts #
        self._contract = the_escrow_contract
        self.deployment_receipts = deployment_receipts
        return deployment_receipts


class PolicyManagerDeployer(BaseContractDeployer, UpgradeableContractMixin, OwnableContractMixin):
    """
    Depends on StakingEscrow and NucypherTokenAgent
    """

    agency = PolicyManagerAgent
    contract_name = agency.registry_contract_name
    deployment_steps = ('deployment', 'dispatcher_deployment', 'set_policy_manager')
    _proxy_deployer = DispatcherDeployer


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        proxy_name = StakingEscrowDeployer._proxy_deployer.contract_name
        staking_contract_name = StakingEscrowDeployer.contract_name
        self.staking_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                     name=staking_contract_name,
                                                                     proxy_name=proxy_name)

    def _deploy_essential(self, gas_limit: int = None) -> tuple:
        policy_manager_contract, deploy_receipt = self.blockchain.deploy_contract(self.deployer_address,
                                                                                  self.registry,
                                                                                  self.contract_name,
                                                                                  self.staking_contract.address,
                                                                                  gas_limit=gas_limit)
        return policy_manager_contract, deploy_receipt

    def deploy(self,
               initial_deployment: bool = True,
               secret_hash: bytes = None,
               gas_limit: int = None,
               progress=None
               ) -> Dict[str, dict]:

        if initial_deployment and not secret_hash:
            raise ValueError(f"An upgrade secret hash is required to perform an initial"
                             f" deployment series for {self.contract_name}.")

        self.check_deployment_readiness()

        # Creator deploys the policy manager
        policy_manager_contract, deploy_receipt = self._deploy_essential(gas_limit=gas_limit)

        # This is the end of bare deployment.
        if not initial_deployment:
            self._contract = policy_manager_contract
            return self._finish_bare_deployment(deployment_receipt=deploy_receipt,
                                                progress=progress)

        if progress:
            progress.update(1)

        proxy_deployer = self._proxy_deployer(registry=self.registry,
                                              target_contract=policy_manager_contract,
                                              deployer_address=self.deployer_address)

        proxy_deploy_receipt = proxy_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)
        proxy_deploy_receipt = proxy_deploy_receipt[proxy_deployer.deployment_steps[0]]
        if progress:
            progress.update(1)

        # Cache the dispatcher contract
        proxy_contract = proxy_deployer.contract
        self.__proxy_contract = proxy_contract

        # Wrap the PolicyManager contract, and use this wrapper
        wrapped_contract = self.blockchain._wrap_contract(wrapper_contract=proxy_contract,
                                                          target_contract=policy_manager_contract)

        # Configure the StakingEscrow contract by setting the PolicyManager
        tx_args = {}
        if gas_limit:
            tx_args.update({'gas': gas_limit})
        set_policy_manager_function = self.staking_contract.functions.setPolicyManager(wrapped_contract.address)
        set_policy_manager_receipt = self.blockchain.send_transaction(contract_function=set_policy_manager_function,
                                                                      sender_address=self.deployer_address,
                                                                      payload=tx_args)
        if progress:
            progress.update(1)

        # Gather the transaction receipts
        ordered_receipts = (deploy_receipt, proxy_deploy_receipt, set_policy_manager_receipt)
        deployment_receipts = dict(zip(self.deployment_steps, ordered_receipts))

        self.deployment_receipts = deployment_receipts
        self._contract = wrapped_contract
        return deployment_receipts


class LibraryLinkerDeployer(BaseContractDeployer, OwnableContractMixin):

    contract_name = 'UserEscrowLibraryLinker'
    deployment_steps = ('contract_deployment', )

    def __init__(self, target_contract: Contract, bare: bool = False, *args, **kwargs):
        self.target_contract = target_contract
        super().__init__(*args, **kwargs)
        if bare:
            self._contract = self.blockchain.get_proxy_contract(registry=self.registry,
                                                                target_address=self.target_contract.address,
                                                                proxy_name=self.contract_name)

    def deploy(self, secret_hash: bytes, gas_limit: int = None, progress=None) -> dict:
        linker_args = (self.target_contract.address, secret_hash)
        linker_contract, receipt = self.blockchain.deploy_contract(self.deployer_address,
                                                                   self.registry,
                                                                   self.contract_name,
                                                                   *linker_args,
                                                                   gas_limit=gas_limit)
        if progress:
            progress.update(1)

        self._contract = linker_contract
        return {self.deployment_steps[0]: receipt}

    @validate_secret
    def retarget(self, new_target: str, existing_secret_plaintext: bytes, new_secret_hash: bytes, gas_limit: int = None):
        if new_target == self.target_contract.address:
            raise self.ContractDeploymentError(f"{new_target} is already targeted by {self.contract_name}: {self._contract.address}")
        if new_target == self._contract.address:
            raise self.ContractDeploymentError(f"{self.contract_name} {self._contract.address} cannot target itself.")

        origin_args = {}  # TODO: Gas management
        if gas_limit:
            origin_args.update({'gas': gas_limit})
        retarget_function = self._contract.functions.upgrade(new_target, existing_secret_plaintext, new_secret_hash)
        retarget_receipt = self.blockchain.send_transaction(contract_function=retarget_function,
                                                            sender_address=self.deployer_address,
                                                            payload=origin_args)
        return retarget_receipt


class UserEscrowProxyDeployer(BaseContractDeployer, UpgradeableContractMixin):

    contract_name = 'UserEscrowProxy'
    deployment_steps = ('contract_deployment', 'linker_deployment')
    number_of_deployment_transactions = 2
    _proxy_deployer = LibraryLinkerDeployer
    _ownable = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        token_contract_name = NucypherTokenDeployer.contract_name
        self.token_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                   name=token_contract_name)

        staking_contract_name = StakingEscrowDeployer.contract_name
        staking_proxy_name = StakingEscrowDeployer._proxy_deployer.contract_name
        self.staking_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                     name=staking_contract_name,
                                                                     proxy_name=staking_proxy_name)

        policy_contract_name = PolicyManagerDeployer.contract_name
        policy_proxy_name = PolicyManagerDeployer._proxy_deployer.contract_name
        self.policy_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                    name=policy_contract_name,
                                                                    proxy_name=policy_proxy_name)

    def _deploy_essential(self, gas_limit: int = None):
        """Note: These parameters are order-sensitive"""
        constructor_args = (self.token_contract.address,
                            self.staking_contract.address,
                            self.policy_contract.address)

        contract, deployment_receipt = self.blockchain.deploy_contract(self.deployer_address,
                                                                       self.registry,
                                                                       self.contract_name,
                                                                       *constructor_args,
                                                                       gas_limit=gas_limit)
        return contract, deployment_receipt

    def deploy(self,
               initial_deployment: bool = True,
               secret_hash: bytes = None,
               gas_limit: int = None,
               progress=None
               ) -> dict:
        """
        Deploys a new UserEscrowProxy contract, and a new UserEscrowLibraryLinker, targeting the first.
        This is meant to be called only once per general deployment.
        """

        if initial_deployment and not secret_hash:
            raise ValueError(f"An upgrade secret hash is required to perform an initial"
                             f" deployment series for {self.contract_name}.")

        # 1 - UserEscrowProxy
        user_escrow_proxy_contract, deployment_receipt = self._deploy_essential(gas_limit=gas_limit)

        # This is the end of bare deployment.
        if not initial_deployment:
            self._contract = user_escrow_proxy_contract
            return self._finish_bare_deployment(deployment_receipt=deployment_receipt,
                                                progress=progress)

        if progress:
            progress.update(1)

        # 2 - UserEscrowLibraryLinker
        linker_deployer = self._proxy_deployer(registry=self.registry,
                                               deployer_address=self.deployer_address,
                                               target_contract=user_escrow_proxy_contract)

        linker_deployment_receipts = linker_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)
        linker_deployment_receipt = linker_deployment_receipts[linker_deployer.deployment_steps[0]]
        if progress:
            progress.update(1)

        # Gather the transaction receipts
        ordered_receipts = (deployment_receipt, linker_deployment_receipt)
        deployment_receipts = dict(zip(self.deployment_steps, ordered_receipts))

        self._contract = user_escrow_proxy_contract
        return deployment_receipts


class UserEscrowDeployer(BaseContractDeployer, UpgradeableContractMixin, OwnableContractMixin):

    agency = UserEscrowAgent
    contract_name = agency.registry_contract_name
    deployment_steps = ('contract_deployment', )
    _linker_deployer = LibraryLinkerDeployer
    __allocation_registry = AllocationRegistry

    def __init__(self, allocation_registry: AllocationRegistry = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        token_contract_name = NucypherTokenDeployer.contract_name
        self.token_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                   name=token_contract_name)
        self.__beneficiary_address = NO_BENEFICIARY
        self.__allocation_registry = allocation_registry or self.__allocation_registry()

    def make_agent(self) -> EthereumContractAgent:
        if self.__beneficiary_address is NO_BENEFICIARY:
            raise self.ContractDeploymentError("No beneficiary assigned to {}".format(self.contract.address))
        agent = self.agency(registry=self.registry,
                            beneficiary=self.__beneficiary_address,
                            allocation_registry=self.__allocation_registry)
        return agent

    @property
    def allocation_registry(self):
        return self.__allocation_registry

    def assign_beneficiary(self, beneficiary_address: str) -> dict: 
        """Relinquish ownership of a UserEscrow deployment to the beneficiary"""
        if not is_checksum_address(beneficiary_address):
            raise self.ContractDeploymentError("{} is not a valid checksum address.".format(beneficiary_address))
        # TODO: #413, #842 - Gas Management
        payload = {'gas': 500_000}
        transfer_owner_function = self.contract.functions.transferOwnership(beneficiary_address)
        transfer_owner_receipt = self.blockchain.send_transaction(contract_function=transfer_owner_function,
                                                                  sender_address=self.deployer_address,
                                                                  payload=payload)
        self.__beneficiary_address = beneficiary_address
        return transfer_owner_receipt

    def initial_deposit(self, value: int, duration_seconds: int) -> dict:
        """Allocate an amount of tokens with lock time in seconds, and transfer ownership to the beneficiary"""
        # Approve
        allocation_receipts = dict()
        approve_function  = self.token_contract.functions.approve(self.contract.address, value)
        approve_receipt = self.blockchain.send_transaction(contract_function=approve_function,
                                                           sender_address=self.deployer_address)  # TODO: Gas
        allocation_receipts['approve'] = approve_receipt

        # Deposit
        # TODO: #413, #842 - Gas Management
        args = {'gas': 200_000}
        deposit_function = self.contract.functions.initialDeposit(value, duration_seconds)
        deposit_receipt = self.blockchain.send_transaction(contract_function=deposit_function,
                                                           sender_address=self.deployer_address,
                                                           payload=args)

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

        deposit_receipt = self.initial_deposit(value=value, duration_seconds=duration)
        assign_receipt = self.assign_beneficiary(beneficiary_address=beneficiary_address)
        self.enroll_principal_contract()
        return dict(deposit_receipt=deposit_receipt, assign_receipt=assign_receipt)

    def deploy(self, initial_deployment: bool = True, gas_limit: int = None, progress=None) -> dict:
        """Deploy a new instance of UserEscrow to the blockchain."""
        self.check_deployment_readiness()
        linker_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                               name=self._linker_deployer.contract_name)
        args = (self.deployer_address,
                self.registry,
                self.contract_name,
                linker_contract.address,
                self.token_contract.address)

        user_escrow_contract, deploy_receipt = self.blockchain.deploy_contract(*args, gas_limit=gas_limit, enroll=False)
        if progress:
            progress.update(1)

        self._contract = user_escrow_contract
        self.deployment_receipts.update({'deployment': deploy_receipt})
        return deploy_receipt


class AdjudicatorDeployer(BaseContractDeployer, UpgradeableContractMixin, OwnableContractMixin):

    agency = AdjudicatorAgent
    contract_name = agency.registry_contract_name
    deployment_steps = ('contract_deployment', 'dispatcher_deployment', 'set_adjudicator')
    _proxy_deployer = DispatcherDeployer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        staking_contract_name = StakingEscrowDeployer.contract_name
        proxy_name = StakingEscrowDeployer._proxy_deployer.contract_name
        self.staking_contract = self.blockchain.get_contract_by_name(registry=self.registry,
                                                                     name=staking_contract_name,
                                                                     proxy_name=proxy_name)

    def _deploy_essential(self, gas_limit: int = None):
        constructor_args = (self.staking_contract.address,
                            *self.economics.slashing_deployment_parameters)
        adjudicator_contract, deploy_receipt = self.blockchain.deploy_contract(self.deployer_address,
                                                                               self.registry,
                                                                               self.contract_name,
                                                                               *constructor_args,
                                                                               gas_limit=gas_limit)
        return adjudicator_contract, deploy_receipt

    def deploy(self,
               initial_deployment: bool = True,
               secret_hash: bytes = None,
               gas_limit: int = None,
               progress=None) -> Dict[str, str]:

        if initial_deployment and not secret_hash:
            raise ValueError(f"An upgrade secret hash is required to perform an initial"
                             f" deployment series for {self.contract_name}.")

        self.check_deployment_readiness()

        adjudicator_contract, deploy_receipt = self._deploy_essential(gas_limit=gas_limit)

        # This is the end of bare deployment.
        if not initial_deployment:
            self._contract = adjudicator_contract
            return self._finish_bare_deployment(deployment_receipt=deploy_receipt,
                                                progress=progress)

        if progress:
            progress.update(1)

        proxy_deployer = self._proxy_deployer(registry=self.registry,
                                              target_contract=adjudicator_contract,
                                              deployer_address=self.deployer_address)

        proxy_deploy_receipts = proxy_deployer.deploy(secret_hash=secret_hash, gas_limit=gas_limit)
        proxy_deploy_receipt = proxy_deploy_receipts[proxy_deployer.deployment_steps[0]]
        if progress:
            progress.update(1)

        # Cache the dispatcher contract
        proxy_contract = proxy_deployer.contract
        self.__proxy_contract = proxy_contract

        # Wrap the escrow contract
        wrapped = self.blockchain._wrap_contract(proxy_contract, target_contract=adjudicator_contract)

        # Switch the contract for the wrapped one
        adjudicator_contract = wrapped

        # Configure the StakingEscrow contract by setting the Adjudicator
        tx_args = {}
        if gas_limit:
            tx_args.update({'gas': gas_limit})
        set_adjudicator_function = self.staking_contract.functions.setAdjudicator(adjudicator_contract.address)
        set_adjudicator_receipt = self.blockchain.send_transaction(contract_function=set_adjudicator_function,
                                                                   sender_address=self.deployer_address,
                                                                   payload=tx_args)
        if progress:
            progress.update(1)

        # Gather the transaction receipts
        ordered_receipts = (deploy_receipt, proxy_deploy_receipt, set_adjudicator_receipt)
        deployment_receipts = dict(zip(self.deployment_steps, ordered_receipts))

        self.deployment_receipts = deployment_receipts
        self._contract = adjudicator_contract

        return deployment_receipts
