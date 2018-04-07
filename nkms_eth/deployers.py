from abc import ABC, abstractmethod
from typing import Tuple, Dict

from populus.contracts.contract import PopulusContract

from nkms_eth.config import NuCypherMinerConfig, NuCypherTokenConfig
from .blockchain import TheBlockchain


class ContractDeployer:

    _contract_name = NotImplemented
    _arming_word = "I UNDERSTAND"

    class ContractDeploymentError(Exception):
        pass

    def __init__(self, blockchain: TheBlockchain):
        self.__armed = False
        self._contract = None
        self.deployment_receipt = None
        self.__dispatcher = NotImplemented

        # Sanity check
        if not isinstance(blockchain, TheBlockchain):
            error = 'Only TheBlockchain can be used to create a deployer, got {}.'
            raise ValueError(error.format(type(blockchain)))
        self.blockchain = blockchain

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
    def displatcher(self):
        return self.__dispatcher

    @property
    def is_deployed(self) -> bool:
        return bool(self._contract is not None)

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

            (self.blockchain._chain.provider.are_contract_dependencies_available(self._contract_name),
             'Blockchain contract dependencies unmet')

            )

        reasons, ready = list(), True
        for rule, failure_reason in rules:
            if not rule:                            # If this rule fails...
                ready = False                       # it's not ready to be deployed

                if fail is True:
                    raise self.ContractDeploymentError(failure_reason)
                else:
                    reasons.append(failure_reason)  # ...and here's why
                    continue

        return ready, reasons

    def _ensure_contract_deployment(self) -> None:
        """Raises ContractDeploymentError if the contract has not been armed and deployed."""

        if self._contract is None:
            class_name = self.__class__.__name__
            message = '{} contract is not deployed. Arm, then deploy.'.format(class_name)
            raise self.ContractDeploymentError(message)

        # http: // populus.readthedocs.io / en / latest / chain.contracts.html  # checking-availability-of-contracts
        available = bool(self.blockchain._chain.provider.are_contract_dependencies_available(self._contract_name))
        if not available:
            raise self.ContractDeploymentError('Contract is not available')

    def _wrap_government(self, dispatcher_contract: PopulusContract, target_contract: PopulusContract) -> PopulusContract:

        # Wrap the contract
        wrapped_contract = self.blockchain._chain.web3.eth.contract(target_contract.abi,
                                                                           dispatcher_contract.address,
                                                                           ContractFactoryClass=PopulusContract)
        return wrapped_contract

    def arm(self, fail_on_abort=True) -> None:
        """
        Safety mechanism for ethereum contract deployment

        If the blockchain network being deployed is not in the testchains tuple,
        user interaction is required to enter the arming word.

        If fail_on_abort is True, raise a configuration Error if the user
        incorrectly types the arming_word.

        """

        # self.check_ready_to_deploy(fail=True)

        # If the blockchain network is public, prompt the user
        if self.blockchain._network not in self.blockchain.test_chains:
            message = """
            Are you sure you want to deploy {} on the {} network?
            
            Type {} to arm the deployer.
            """.format(self._arming_word, self._contract_name, self.blockchain._network)

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

    def deploy(self) -> str:
        """
        Used after arming the deployer;
        Provides for the setup, deployment, and initialization of ethereum smart contracts.
        Emits the configured blockchain network transactions for single contract instance publication.
        """
        raise NotImplementedError


class NuCypherKMSTokenDeployer(ContractDeployer, NuCypherTokenConfig):

    _contract_name = 'NuCypherKMSToken'

    def __init__(self, blockchain):
        super().__init__(blockchain=blockchain)
        self._creator = self.blockchain._chain.web3.eth.accounts[0]

    def deploy(self) -> str:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!
        """

        self.check_ready_to_deploy(fail=True)

        the_nucypher_token_contract, deployment_txhash = self.blockchain._chain.provider.deploy_contract(
            self._contract_name,
            deploy_args=[self.saturation],
            deploy_transaction={'from': self._creator})

        self.blockchain.wait_for_receipt(deployment_txhash)
        self._contract = the_nucypher_token_contract
        self.deployment_receipt = deployment_txhash

        return self.deployment_receipt


class DispatcherDeployer(ContractDeployer):
    """
    Take another contract as an arg
    """

    _contract_name = 'Dispatcher'

    def __init__(self, token_agent, target_contract):
        self.token_agent = token_agent
        self.target_contract = target_contract
        super().__init__(blockchain=token_agent.blockchain)

    def deploy(self):
        dispatcher_contract, txhash = self.blockchain._chain.provider.deploy_contract(
            'Dispatcher', deploy_args=[self.target_contract.address],
            deploy_transaction={'from': self.token_agent.origin})

        self._contract = dispatcher_contract
        return txhash


class MinerEscrowDeployer(ContractDeployer, NuCypherMinerConfig):
    """
    Deploys the MinerEscrow ethereum contract to the blockchain.  Depends on NuCypherTokenAgent
    """

    _contract_name = 'MinersEscrow'

    def __init__(self, token_agent):
        super().__init__(blockchain=token_agent.blockchain)
        self.token_agent = token_agent

    def deploy(self) -> Dict[str]:
        """
        Deploy and publish the NuCypherKMS Token contract
        to the blockchain network specified in self.blockchain.network.

        The contract must be armed before it can be deployed.
        Deployment can only ever be executed exactly once!

        Emits the folowing blockchain network transactions:
            - MinerEscrow contract deployment
            - MinerEscrow dispatcher deployment
            - Transfer reward tokens origin -> MinerEscrow contract
            - MinerEscrow contract initialization

        Returns transaction hashes in a tuple.
        """

        # Raise if not all-systems-go
        self.check_ready_to_deploy(fail=True)

        # Build deployment arguments
        deploy_args = [self.token_agent.contract_address] + self.mining_coefficient    # config
        origin_args = {'from': self.token_agent.origin}

        # 1 - Deploy #
        the_escrow_contract, deploy_txhash = self.blockchain._chain.provider.\
            deploy_contract(self._contract_name,
                            deploy_args=deploy_args,
                            deploy_transaction=origin_args)
        deploy_receipt = self.blockchain.wait_for_receipt(deploy_txhash)

        # 2 - Deploy the dispatcher used for updating this contract #
        dispatcher_deployer = DispatcherDeployer(token_agent=self.token_agent, target_contract=the_escrow_contract)
        dispatcher_deployer.arm(fail_on_abort=True)
        dispatcher_deploy_txhash = dispatcher_deployer.deploy()

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer._contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract (Govern)
        wrapped_escrow_contract = self._wrap_government(dispatcher_contract,
                                                        target_contract=the_escrow_contract)

        # Switch the contract for the wrapped one
        the_escrow_contract = wrapped_escrow_contract

        # 3 - Transfer tokens to the miner escrow #
        reward_txhash = self.token_agent.transact(origin_args).transfer(the_escrow_contract.address, self.reward)
        reward_receipt = self.blockchain.wait_for_receipt(reward_txhash)

        # 4 - Initialize the Miner Escrow contract
        init_txhash = the_escrow_contract.transact().initialize()
        init_receipt = self.blockchain.wait_for_receipt(init_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deploy': deploy_txhash,
                                   'dispatcher_deploy': dispatcher_deploy_txhash,
                                   'reward_transfer': reward_txhash,
                                   'initialize': init_txhash}

        # Set the contract and transaction hashes #
        self._contract = the_escrow_contract
        self.deployment_transactions = deployment_transactions
        return deployment_transactions


class PolicyManagerDeployer(ContractDeployer):
    """
    Depends on MinerAgent and NuCypherTokenAgent
    """

    _contract_name = 'PolicyManager'

    def __init__(self, miner_agent):
        self.token_agent = miner_agent.token_agent
        self.miner_agent = miner_agent
        super().__init__(blockchain=self.token_agent.blockchain)

    def deploy(self) -> Tuple[str, str]:
        self.check_ready_to_deploy(fail=True)

        # Creator deploys the policy manager
        the_policy_manager_contract, deploy_txhash = self.blockchain._chain.provider.deploy_contract(
            self._contract_name,
            deploy_args=[self.miner_agent.contract_address],
            deploy_transaction={'from': self.token_agent.origin})

        dispatcher_deployer = DispatcherDeployer(token_agent=self.token_agent, target_contract=the_policy_manager_contract)
        dispatcher_deployer.arm(fail_on_abort=True)
        dispatcher_deploy_txhash = dispatcher_deployer.deploy()

        # Cache the dispatcher contract
        dispatcher_contract = dispatcher_deployer._contract
        self.__dispatcher_contract = dispatcher_contract

        # Wrap the escrow contract (Govern)
        wrapped_policy_manager_contract = self._wrap_government(dispatcher_contract,
                                                                target_contract=the_policy_manager_contract)

        # Switch the contract for the wrapped one
        the_policy_manager_contract = wrapped_policy_manager_contract

        # Configure the MinerEscrow by setting the PolicyManager
        policy_setter_txhash = self.miner_agent.transact({'from': self.token_agent.origin}).\
            setPolicyManager(the_policy_manager_contract.address)

        self.blockchain.wait_for_receipt(policy_setter_txhash)

        # Gather the transaction hashes
        deployment_transactions = {'deployment': deploy_txhash,
                                   'dispatcher_deployment': dispatcher_deploy_txhash,
                                   'set_policy_manager': policy_setter_txhash}

        self.deployment_transactions = deployment_transactions
        self._contract = the_policy_manager_contract

        return deployment_transactions
