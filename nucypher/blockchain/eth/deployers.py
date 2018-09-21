from constant_sorrow import constants
from typing import Tuple, Dict

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
    _arming_word = "I UNDERSTAND"

    class ContractDeploymentError(Exception):
        pass

    def __init__(self,
                 blockchain: Blockchain,
                 deployer_address: str
                 ) -> None:

        self.__armed = False
        self._contract = constants.CONTRACT_NOT_DEPLOYED
        self.deployment_receipt = constants.CONTRACT_NOT_DEPLOYED
        self.__dispatcher = NotImplemented

        # Sanity check
        if not isinstance(blockchain, Blockchain):
            error = 'Only TheBlockchain can be used to create a deployer, got {}.'
            raise ValueError(error.format(type(blockchain)))
        self.blockchain = blockchain
        self.__deployer_address = deployer_address

    @property
    def contract_address(self) -> str:
        if self._contract is constants.CONTRACT_NOT_DEPLOYED:
            cls = self.__class__
            raise ContractDeployer.ContractDeploymentError('Contract not deployed')
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
        return self.__dispatcher

    @property
    def is_deployed(self) -> bool:
        return bool(self._contract is not constants.CONTRACT_NOT_DEPLOYED)

    @property
    def is_armed(self) -> bool:
        return bool(self.__armed is True)

    def check_ready_to_deploy(self, fail=False) -> Tuple[bool, list]:
        """
        Iterates through a set of rules required for an ethereum
        contract deployer to be eligible for deployment returning a
        tuple or raising an exception if <fail> is True.

        Returns a tuple containing the boolean readiness result and a list of reasons (if any)
        why the deployer is not ready.

        If fail is set to True, raise a configuration error, instead of returning.
        """

        rules = (
            (self.is_armed is True, 'Contract not armed'),
            (self.is_deployed is not True, 'Contract already deployed'),
            (self.deployer_address is not constants.NO_DEPLOYER_CONFIGURED, 'No deployer origin address set.'),

            )

        disqualifications = list()
        for failed_rule, failure_reason in rules:
            if failed_rule is False:                           # If this rule fails...
                if fail is True:
                    raise self.ContractDeploymentError(failure_reason)
                else:
                    disqualifications.append(failure_reason)  # ...and here's why
                    continue

        is_ready = True if len(disqualifications) == 0 else False
        return is_ready, disqualifications

    def _ensure_contract_deployment(self) -> bool:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""

        if self._contract is constants.CONTRACT_NOT_DEPLOYED:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)

        return True

    def arm(self, fail_on_abort: bool = True) -> None:
        """
        Safety mechanism for ethereum contract deployment

        If the blockchain network being deployed is not in the testchains tuple,
        user interaction is required to enter the arming word.

        If fail_on_abort is True, raise a configuration Error if the user
        incorrectly types the arming_word.

        """
        if self.__armed is True:
            raise self.ContractDeploymentError('{} deployer is already armed.'.format(self._contract_name))

        # If the blockchain network is public, prompt the user
        if self.blockchain.interface.network not in self.blockchain.test_chains:
            message = """
            Are you sure you want to deploy {contract} on the {network} network?
            
            Type {word} to arm the deployer.
            """.format(contract=self._contract_name, network=self.blockchain.interface.network, word=self._arming_word)

            answer = input(message)
            if answer == self._arming_word:
                arm = True
                outcome_message = '{} is armed!'.format(self.__class__.__name__)
            else:
                arm = False
                outcome_message = '{} was not armed.'.format(self.__class__.__name__)

                if fail_on_abort is True:
                    raise self.ContractDeploymentError("User aborted deployment")

            print(outcome_message)
        else:
            arm = True      # If this is a private chain, just arm the deployer without interaction.
        self.__armed = arm  # Set the arming status

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
    _contract_name = agency.principal_contract_name  # TODO

    def __init__(self,
                 blockchain,
                 deployer_address: str
                 ) -> None:

        if not type(blockchain.interface) is self._interface_class:
            raise ValueError("{} must be used to create a {}".format(self._interface_class.__name__,
                                                                     self.__class__.__name__))

        super().__init__(blockchain=blockchain, deployer_address=deployer_address)
        self._creator = deployer_address

    def deploy(self) -> dict:
        """
        Deploy and publish the NuCypher Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!
        """

        is_ready, _disqualifications = self.check_ready_to_deploy(fail=True)
        assert is_ready

        _contract, deployment_txhash = self.blockchain.interface.deploy_contract(
                                       self._contract_name,
                                       int(constants.TOKEN_SATURATION))

        self._contract = _contract
        return {'deployment_receipt': self.deployment_receipt}


class DispatcherDeployer(ContractDeployer):
    """
    Ethereum smart contract that acts as a proxy to another ethereum contract,
    used as a means of "dispatching" the correct version of the contract to the client
    """

    _contract_name = 'Dispatcher'

    def __init__(self, target_contract, secret_hash, *args, **kwargs):
        self.target_contract = target_contract
        self.secret_hash = secret_hash
        super().__init__(*args, **kwargs)

    def deploy(self) -> dict:

        dispatcher_contract, txhash = self.blockchain.interface.deploy_contract('Dispatcher',
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
        super().__init__(blockchain=token_agent.blockchain, *args, **kwargs)
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
        is_ready, _disqualifications = self.check_ready_to_deploy(fail=True)
        assert is_ready

        # Build deployment arguments
        origin_args = {'from': self.deployer_address}

        # 1 - Deploy #
        the_escrow_contract, deploy_txhash, = \
            self.blockchain.interface.deploy_contract(self._contract_name,
                                                      self.token_agent.contract_address,
                                                      *map(int, constants.MINING_COEFFICIENT))

        # 2 - Deploy the dispatcher used for updating this contract #
        dispatcher_deployer = DispatcherDeployer(blockchain=self.token_agent.blockchain,
                                                 target_contract=the_escrow_contract,
                                                 deployer_address=self.deployer_address,
                                                 secret_hash=self.secret_hash)

        dispatcher_deployer.arm(fail_on_abort=True)
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
                                                                     int(constants.TOKEN_SUPPLY)).transact(origin_args)

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
        super().__init__(blockchain=self.miner_agent.blockchain, *args, **kwargs)

    def deploy(self) -> Dict[str, str]:
        is_ready, _disqualifications = self.check_ready_to_deploy(fail=True)
        assert is_ready

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self.blockchain.interface.deploy_contract(
            self._contract_name, self.miner_agent.contract_address)

        dispatcher_deployer = DispatcherDeployer(blockchain=self.token_agent.blockchain,
                                                 target_contract=the_policy_manager_contract,
                                                 deployer_address=self.deployer_address,
                                                 secret_hash=self.secret_hash)

        dispatcher_deployer.arm(fail_on_abort=True)
        dispatcher_deploy_txhash = dispatcher_deployer.deploy()

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer.contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract (Govern)
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


class UserEscrowDeployer(ContractDeployer):
    """
    TODO: Consider Agency amongst many user escrows,
    goverment, token transfer, and deployment

    Depends on Token, MinerEscrow, and PolicyManager
    """

    agency = UserEscrowAgent
    _contract_name = agency.principal_contract_name

    def __init__(self, miner_escrow_deployer, policy_deployer, *args, **kwargs) -> None:
        self.miner_deployer = miner_escrow_deployer
        self.policy_deployer = policy_deployer
        self.token_deployer = miner_escrow_deployer.token_deployer
        super().__init__(blockchain=miner_escrow_deployer.blockchain, *args, **kwargs)

    def deploy(self) -> dict:
        is_ready, _disqualifications = self.check_ready_to_deploy(fail=True)
        assert is_ready

        deployment_args = [self.token_deployer.contract_address,
                           self.miner_deployer.contract_address,
                           self.policy_deployer.contract_address]

        deploy_transaction = {'from': self.token_deployer.contract_address}  # TODO:.. eh?

        the_user_escrow_contract, deploy_txhash = self.blockchain.interface.deploy_contract(
            self._contract_name,
            *deployment_args)

        self._contract = the_user_escrow_contract
        return {'deploy_txhash': deploy_txhash}
