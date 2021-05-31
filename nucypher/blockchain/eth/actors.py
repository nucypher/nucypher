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


import json
import os
from decimal import Decimal
from typing import Callable, Union
from typing import Dict, Iterable, List, Optional, Tuple

import maya
import time
from constant_sorrow.constants import FULL, WORKER_NOT_RUNNING
from eth_tester.exceptions import TransactionFailed as TestTransactionFailed
from eth_typing import ChecksumAddress
from eth_utils import to_canonical_address
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import ValidationError
from web3.types import TxReceipt

from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.economics import (
    BaseEconomics,
    EconomicsFactory,
    StandardTokenEconomics
)
from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    MultiSigAgent,
    NucypherTokenAgent,
    PolicyManagerAgent,
    StakersReservoir,
    StakingEscrowAgent,
    TokenManagerAgent,
    VotingAgent,
    VotingAggregatorAgent,
    WorkLockAgent,
    AragonAgent
)
from nucypher.blockchain.eth.aragon import CallScriptCodec, DAORegistry, Action
from nucypher.blockchain.eth.constants import (
    NULL_ADDRESS,
    EMERGENCY_MANAGER,
    STANDARD_AGGREGATOR,
    STANDARD_VOTING,
    DAO_AGENT,
    POLICY_MANAGER_CONTRACT_NAME,
    DISPATCHER_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME
)
from nucypher.blockchain.eth.decorators import (
    only_me,
    save_receipt,
    validate_checksum_address
)
from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    BaseContractDeployer,
    MultiSigDeployer,
    NucypherTokenDeployer,
    PolicyManagerDeployer,
    StakingEscrowDeployer,
    StakingInterfaceDeployer,
    WorklockDeployer
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.multisig import Authorization, Proposal
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.blockchain.eth.token import (
    NU,
    Stake,
    StakeList,
    WorkTracker,
    validate_prolong,
    validate_increase,
    validate_divide,
    validate_merge
)
from nucypher.blockchain.eth.utils import (
    calculate_period_duration,
    datetime_at_period,
    datetime_to_period,
    prettify_eth_amount
)
from nucypher.characters.banners import STAKEHOLDER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import TransactingPower
from nucypher.types import NuNits, Period
from nucypher.utilities.logging import Logger


class BaseActor:
    """
    Concrete base class for any actor that will interface with NuCypher's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    @validate_checksum_address
    def __init__(self,
                 domain: Optional[str],
                 registry: BaseContractRegistry,
                 transacting_power: Optional[TransactingPower] = None,
                 checksum_address: Optional[ChecksumAddress] = None):

        if not (bool(checksum_address) ^ bool(transacting_power)):
            error = f'Pass transacting power or checksum address, got {checksum_address} and {transacting_power}.'
            raise ValueError(error)

        try:
            parent_address = self.checksum_address
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError(f"Can't have two different ethereum addresses. "
                                     f"Got {parent_address} and {checksum_address}.")
        except AttributeError:
            if transacting_power:
                self.checksum_address = transacting_power.account
            else:
                self.checksum_address = checksum_address

        self.transacting_power = transacting_power
        self.registry = registry
        self.network = domain
        self._saved_receipts = list()  # track receipts of transmitted transactions

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_address)
        return r

    def __eq__(self, other) -> bool:
        """Actors are equal if they have the same address."""
        try:
            return bool(self.checksum_address == other.checksum_address)
        except AttributeError:
            return False

    @property
    def eth_balance(self) -> Decimal:
        """Return this actor's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
        balance = blockchain.client.get_balance(self.checksum_address)
        return Web3.fromWei(balance, 'ether')


class NucypherTokenActor(BaseActor):
    """
    Actor to interface with the NuCypherToken contract
    """

    def __init__(self, registry: BaseContractRegistry, **kwargs):
        super().__init__(registry=registry, **kwargs)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)

    @property
    def token_balance(self) -> NU:
        """Return this actor's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance


class ContractAdministrator(BaseActor):
    """
    The administrator of network contracts.
    """

    # Note: Deployer classes are sorted by deployment dependency order.

    standard_deployer_classes = (
        NucypherTokenDeployer,
    )

    dispatched_upgradeable_deployer_classes = (
        StakingEscrowDeployer,
        PolicyManagerDeployer,
        AdjudicatorDeployer,
    )

    upgradeable_deployer_classes = (
        *dispatched_upgradeable_deployer_classes,
        StakingInterfaceDeployer,
    )

    aux_deployer_classes = (
        WorklockDeployer,
        MultiSigDeployer,
    )

    # For ownership transfers.
    ownable_deployer_classes = (*dispatched_upgradeable_deployer_classes,
                                StakingInterfaceDeployer)

    # Used in the automated deployment series.
    primary_deployer_classes = (*standard_deployer_classes,
                                *upgradeable_deployer_classes)

    # Comprehensive collection.
    all_deployer_classes = (*primary_deployer_classes,
                            *aux_deployer_classes,
                            *ownable_deployer_classes)

    class UnknownContract(ValueError):
        pass

    def __init__(self, economics: BaseEconomics = None, *args, **kwargs):
        self.log = Logger("Deployment-Actor")
        self.economics = economics or StandardTokenEconomics()
        self.deployers = {d.contract_name: d for d in self.all_deployer_classes}
        super().__init__(*args, **kwargs)

    def __repr__(self):
        r = '{name} - {deployer_address})'.format(name=self.__class__.__name__, deployer_address=self.checksum_address)
        return r

    def __get_deployer(self, contract_name: str):
        try:
            Deployer = self.deployers[contract_name]
        except KeyError:
            raise self.UnknownContract(contract_name)
        return Deployer

    def deploy_contract(self,
                        contract_name: str,
                        gas_limit: int = None,
                        deployment_mode=FULL,
                        ignore_deployed: bool = False,
                        progress=None,
                        confirmations: int = 0,
                        deployment_parameters: dict = None,
                        emitter=None,
                        *args, **kwargs,
                        ) -> Tuple[dict, BaseContractDeployer]:

        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')

        deployment_parameters = deployment_parameters or {}

        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, economics=self.economics, *args, **kwargs)

        if Deployer._upgradeable:
            receipts = deployer.deploy(transacting_power=self.transacting_power,
                                       gas_limit=gas_limit,
                                       progress=progress,
                                       ignore_deployed=ignore_deployed,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       emitter=emitter,
                                       **deployment_parameters)
        else:
            receipts = deployer.deploy(transacting_power=self.transacting_power,
                                       gas_limit=gas_limit,
                                       progress=progress,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       ignore_deployed=ignore_deployed,
                                       emitter=emitter,
                                       **deployment_parameters)
        return receipts, deployer

    def upgrade_contract(self,
                         contract_name: str,
                         confirmations: int,
                         ignore_deployed: bool = False,
                         ) -> dict:
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        receipts = deployer.upgrade(transacting_power=self.transacting_power,
                                    ignore_deployed=ignore_deployed,
                                    confirmations=confirmations)
        return receipts

    def retarget_proxy(self,
                       confirmations: int,
                       contract_name: str,
                       target_address: str,
                       just_build_transaction: bool = False
                       ):
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        result = deployer.retarget(transacting_power=self.transacting_power,
                                   target_address=target_address,
                                   just_build_transaction=just_build_transaction,
                                   confirmations=confirmations)
        return result

    def rollback_contract(self, contract_name: str):
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        receipts = deployer.rollback(transacting_power=self.transacting_power)
        return receipts

    def save_deployment_receipts(self, receipts: dict, filename_prefix: str = 'deployment') -> str:
        config_root = DEFAULT_CONFIG_ROOT  # We force the use of the default here.
        filename = f'{filename_prefix}-receipts-{self.deployer_address[:6]}-{maya.now().epoch}.json'
        filepath = os.path.join(config_root, filename)
        os.makedirs(config_root, exist_ok=True)
        with open(filepath, 'w') as file:
            data = dict()
            for contract_name, contract_receipts in receipts.items():
                contract_records = dict()
                for tx_name, receipt in contract_receipts.items():
                    # Formatting
                    pretty_receipt = {item: str(result) for item, result in receipt.items()}
                    contract_records[tx_name] = pretty_receipt
                data[contract_name] = contract_records
            data = json.dumps(data, indent=4)
            file.write(data)
        return filepath

    def set_fee_rate_range(self,
                           minimum: int,
                           default: int,
                           maximum: int,
                           transaction_gas_limit: int = None) -> TxReceipt:
        if not self.transacting_power:
            raise self.ActorError('No transacting power available.')
        policy_manager_deployer = PolicyManagerDeployer(registry=self.registry, economics=self.economics)
        receipt = policy_manager_deployer.set_fee_rate_range(transacting_power=self.transacting_power,
                                                             minimum=minimum,
                                                             default=default,
                                                             maximum=maximum,
                                                             gas_limit=transaction_gas_limit)
        return receipt


class MultiSigActor(BaseActor):
    class UnknownExecutive(Exception):
        """
        Raised when Executive is not listed as a owner of the MultiSig.
        """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multisig_agent = ContractAgency.get_agent(MultiSigAgent, registry=self.registry)


class Trustee(MultiSigActor):
    """
    A member of a MultiSigBoard given the power and
    obligation to execute an authorized transaction on
    behalf of the board of executives.
    """

    class NoAuthorizations(RuntimeError):
        """Raised when there are zero authorizations."""

    def __init__(self,
                 checksum_address: ChecksumAddress,
                 is_transacting: bool,
                 signer: Optional[Signer] = None,
                 *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)
        self.authorizations = dict()
        self.executive_addresses = tuple(self.multisig_agent.owners)
        if is_transacting:
            if not signer:
                raise ValueError('signer is required to create a transacting Trustee.')
            self.transacting_power = TransactingPower(account=checksum_address, signer=signer)

    def add_authorization(self, authorization, proposal: Proposal) -> str:
        executive_address = authorization.recover_executive_address(proposal)
        if executive_address not in self.executive_addresses:
            raise self.UnknownExecutive(f"Executive {executive_address} is not listed as an owner of the MultiSig.")
        if executive_address in self.authorizations:
            raise ValueError(f"There is already an authorization from executive {executive_address}")

        self.authorizations[executive_address] = authorization
        return executive_address

    def _combine_authorizations(self) -> Tuple[List[bytes], ...]:
        if not self.authorizations:
            raise self.NoAuthorizations

        all_v, all_r, all_s = list(), list(), list()

        def order_by_address(executive_address_to_sort):
            """
            Authorizations (i.e., signatures) must be provided to the MultiSig in increasing order by signing address
            """
            return Web3.toInt(to_canonical_address(executive_address_to_sort))

        for executive_address in sorted(self.authorizations.keys(), key=order_by_address):
            authorization = self.authorizations[executive_address]
            r, s, v = authorization.components
            all_v.append(Web3.toInt(v))  # v values are passed to the contract as ints, not as bytes
            all_r.append(r)
            all_s.append(s)

        return all_r, all_s, all_v

    def execute(self, proposal: Proposal) -> dict:

        if proposal.trustee_address != self.checksum_address:
            raise ValueError(f"This proposal is meant to be executed by trustee {proposal.trustee_address}, "
                             f"not by this trustee ({self.checksum_address})")
        # TODO: check for inconsistencies (nonce, etc.)

        r, s, v = self._combine_authorizations()
        receipt = self.multisig_agent.execute(sender_address=self.checksum_address,
                                              # TODO: Investigate unresolved reference to .execute
                                              v=v, r=r, s=s,
                                              destination=proposal.target_address,
                                              value=proposal.value,
                                              data=proposal.data)
        return receipt

    def create_transaction_proposal(self, transaction):
        proposal = Proposal.from_transaction(transaction,
                                             multisig_agent=self.multisig_agent,
                                             trustee_address=self.checksum_address)
        return proposal

    # MultiSig management proposals

    def propose_adding_owner(self, new_owner_address: str, evidence: str) -> Proposal:
        # TODO: Use evidence to ascertain new owner can transact with this address
        tx = self.multisig_agent.build_add_owner_tx(new_owner_address=new_owner_address)
        proposal = self.create_transaction_proposal(tx)
        return proposal

    def propose_removing_owner(self, owner_address: str) -> Proposal:
        tx = self.multisig_agent.build_remove_owner_tx(owner_address=owner_address)
        proposal = self.create_transaction_proposal(tx)
        return proposal

    def propose_changing_threshold(self, new_threshold: int) -> Proposal:
        tx = self.multisig_agent.build_change_threshold_tx(new_threshold)
        proposal = self.create_transaction_proposal(tx)
        return proposal


class Executive(MultiSigActor):
    """
    An actor having the power to authorize transaction executions to a delegated trustee.
    """

    def __init__(self,
                 checksum_address: ChecksumAddress,
                 signer: Signer = None,
                 *args, **kwargs):
        super().__init__(checksum_address=checksum_address, *args, **kwargs)

        if checksum_address not in self.multisig_agent.owners:
            raise self.UnknownExecutive(f"Executive {checksum_address} is not listed as an owner of the MultiSig. "
                                        f"Current owners are {self.multisig_agent.owners}")
        self.signer = signer
        if signer:
            self.transacting_power = TransactingPower(signer=signer, account=checksum_address)

    def authorize_proposal(self, proposal) -> Authorization:
        # TODO: Double-check that the digest corresponds to the real data to sign
        signature = self.signer.sign_data_for_validator(account=self.checksum_address,
                                                        message=proposal.application_specific_data,
                                                        validator_address=self.multisig_agent.contract_address)
        authorization = Authorization.deserialize(data=Web3.toBytes(hexstr=signature))
        return authorization


class Staker(NucypherTokenActor):
    """
    Baseclass for staking-related operations on the blockchain.
    """

    class StakerError(NucypherTokenActor.ActorError):
        pass

    class InsufficientTokens(StakerError):
        pass

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log = Logger("staker")
        self.is_me = bool(self.transacting_power)
        self._worker_address = None

        # Blockchain
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.economics = EconomicsFactory.get_economics(registry=self.registry)

        # Check stakes
        self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)

    def refresh_stakes(self):
        self.stakes.refresh()

    def to_dict(self) -> dict:
        stake_info = [stake.to_stake_info() for stake in self.stakes]
        worker_address = self.worker_address or NULL_ADDRESS
        staker_funds = {'ETH': int(self.eth_balance), 'NU': int(self.token_balance)}
        staker_payload = {'staker': self.checksum_address,
                          'balances': staker_funds,
                          'worker': worker_address,
                          'stakes': stake_info}
        return staker_payload

    @property
    def is_staking(self) -> bool:
        """Checks if this Staker currently has active stakes / locked tokens."""
        return bool(self.stakes)

    def owned_tokens(self) -> NU:
        """
        Returns all tokens that belong to the staker, including locked, unlocked and rewards.
        """
        raw_value = self.staking_agent.owned_tokens(staker_address=self.checksum_address)
        value = NU.from_nunits(raw_value)
        return value

    def locked_tokens(self, periods: int = 0) -> NU:
        """Returns the amount of tokens this staker has locked for a given duration in periods."""
        raw_value = self.staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=periods)
        value = NU.from_nunits(raw_value)
        return value

    @property
    def current_stake(self) -> NU:
        """The total number of staked tokens, i.e., tokens locked in the current period."""
        return self.locked_tokens(periods=0)

    def filtered_stakes(self,
                        parent_status: Stake.Status = None,
                        filter_function: Callable[[Stake], bool] = None
                        ) -> Iterable[Stake]:
        """Returns stakes for this staker which filtered by status or by a provided function."""
        if not parent_status and not filter_function:
            raise ValueError("Pass parent status or filter function or both.")

        # Read once from chain and reuse these values
        staker_info = self.staking_agent.get_staker_info(self.checksum_address)  # TODO related to #1514
        current_period = self.staking_agent.get_current_period()                 # TODO #1514 this is online only.

        stakes = list()
        for stake in self.stakes:
            if parent_status and not stake.status(staker_info, current_period).is_child(parent_status):
                continue
            if filter_function and not filter_function(stake):
                continue
            stakes.append(stake)

        return stakes

    def sorted_stakes(self,
                      parent_status: Stake.Status = None,
                      filter_function: Callable[[Stake], bool] = None
                      ) -> List[Stake]:
        """Returns a list of filtered stakes sorted by account wallet index."""
        if parent_status is not None or filter_function is not None:
            filtered_stakes = self.filtered_stakes(parent_status, filter_function)
        else:
            filtered_stakes = self.stakes

        stakes = sorted(filtered_stakes, key=lambda s: s.address_index_ordering_key)
        return stakes

    @only_me
    def initialize_stake(self,
                         amount: NU = None,
                         lock_periods: int = None,
                         expiration: maya.MayaDT = None,
                         entire_balance: bool = False,
                         from_unlocked: bool = False
                         ) -> TxReceipt:

        """Create a new stake."""

        # Duration
        if not (bool(lock_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either lock periods or expiration; got {'both' if lock_periods else 'neither'}")
        if expiration:
            lock_periods = calculate_period_duration(future_time=expiration,
                                                     seconds_per_period=self.economics.seconds_per_period)

        # Value
        if entire_balance and amount:
            raise ValueError("Specify an amount or entire balance, not both")
        elif not entire_balance and not amount:
            raise ValueError("Specify an amount or entire balance, got neither")

        token_balance = self.calculate_staking_reward() if from_unlocked else self.token_balance
        if entire_balance:
            amount = token_balance
        if not token_balance >= amount:
            raise self.InsufficientTokens(f"Insufficient token balance ({token_balance}) "
                                          f"for new stake initialization of {amount}")

        # Write to blockchain
        new_stake = Stake.initialize_stake(staking_agent=self.staking_agent,
                                           economics=self.economics,
                                           checksum_address=self.checksum_address,
                                           amount=amount,
                                           lock_periods=lock_periods)

        # Create stake on-chain
        if from_unlocked:
            receipt = self._lock_and_create(amount=new_stake.value.to_nunits(), lock_periods=new_stake.duration)
        else:
            receipt = self._deposit(amount=new_stake.value.to_nunits(), lock_periods=new_stake.duration)

        # Log and return receipt
        self.log.info(f"{self.checksum_address} initialized new stake: {amount} tokens for {lock_periods} periods")

        # Update staking cache element
        self.refresh_stakes()

        return receipt

    def _ensure_stake_exists(self, stake: Stake):
        if len(self.stakes) <= stake.index:
            raise ValueError(f"There is no stake with index {stake.index}")
        if self.stakes[stake.index] != stake:
            raise ValueError(f"Stake with index {stake.index} is not equal to provided stake")

    @only_me
    def divide_stake(self,
                     stake: Stake,
                     target_value: NU,
                     additional_periods: int = None,
                     expiration: maya.MayaDT = None
                     ) -> TxReceipt:
        self._ensure_stake_exists(stake)

        if not (bool(additional_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either the number of lock periods or expiration; "
                             f"got {'both' if additional_periods else 'neither'}")

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration, seconds_per_period=self.economics.seconds_per_period) - stake.final_locked_period
            if additional_periods <= 0:
                raise ValueError(f"New expiration {expiration} must be at least 1 period from the "
                                 f"current stake's end period ({stake.final_locked_period}).")

        # Read on-chain stake and validate
        stake.sync()
        validate_divide(stake=stake, target_value=target_value, additional_periods=additional_periods)

        # Do it already!
        receipt = self._divide_stake(stake_index=stake.index,
                                     additional_periods=additional_periods,
                                     target_value=int(target_value))

        # Update staking cache element
        self.refresh_stakes()

        return receipt

    @only_me
    def increase_stake(self,
                       stake: Stake,
                       amount: NU = None,
                       entire_balance: bool = False,
                       from_unlocked: bool = False
                       ) -> TxReceipt:
        """Add tokens to existing stake."""
        self._ensure_stake_exists(stake)

        # Value
        if not (bool(entire_balance) ^ bool(amount)):
            raise ValueError(f"Pass either an amount or entire balance; "
                             f"got {'both' if entire_balance else 'neither'}")

        token_balance = self.calculate_staking_reward() if from_unlocked else self.token_balance
        if entire_balance:
            amount = token_balance
        if not token_balance >= amount:
            raise self.InsufficientTokens(f"Insufficient token balance ({token_balance}) "
                                          f"to increase stake by {amount}")

        # Read on-chain stake and validate
        stake.sync()
        validate_increase(stake=stake, amount=amount)

        # Write to blockchain
        if from_unlocked:
            receipt = self._lock_and_increase(stake_index=stake.index, amount=int(amount))
        else:
            receipt = self._deposit_and_increase(stake_index=stake.index, amount=int(amount))

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    @only_me
    def prolong_stake(self,
                      stake: Stake,
                      additional_periods: int = None,
                      expiration: maya.MayaDT = None
                      ) -> TxReceipt:
        self._ensure_stake_exists(stake)

        if not (bool(additional_periods) ^ bool(expiration)):
            raise ValueError(f"Pass either the number of lock periods or expiration; "
                             f"got {'both' if additional_periods else 'neither'}")

        # Calculate stake duration in periods
        if expiration:
            additional_periods = datetime_to_period(datetime=expiration,
                                                    seconds_per_period=self.economics.seconds_per_period) - stake.final_locked_period
            if additional_periods <= 0:
                raise ValueError(f"New expiration {expiration} must be at least 1 period from the "
                                 f"current stake's end period ({stake.final_locked_period}).")

        # Read on-chain stake and validate
        stake.sync()
        validate_prolong(stake=stake, additional_periods=additional_periods)

        receipt = self._prolong_stake(stake_index=stake.index, lock_periods=additional_periods)

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    @only_me
    def merge_stakes(self,
                     stake_1: Stake,
                     stake_2: Stake
                     ) -> TxReceipt:
        self._ensure_stake_exists(stake_1)
        self._ensure_stake_exists(stake_2)

        # Read on-chain stake and validate
        stake_1.sync()
        stake_2.sync()
        validate_merge(stake_1=stake_1, stake_2=stake_2)

        receipt = self._merge_stakes(stake_index_1=stake_1.index, stake_index_2=stake_2.index)

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    def _prolong_stake(self, stake_index: int, lock_periods: int) -> TxReceipt:
        """Public facing method for stake prolongation."""
        receipt = self.staking_agent.prolong_stake(stake_index=stake_index,
                                                   periods=lock_periods,
                                                   transacting_power=self.transacting_power)
        return receipt

    def _deposit(self, amount: int, lock_periods: int) -> TxReceipt:
        """Public facing method for token locking."""
        self._ensure_allowance_equals(0)
        receipt = self.token_agent.approve_and_call(amount=amount,
                                                    target_address=self.staking_agent.contract_address,
                                                    transacting_power=self.transacting_power,
                                                    call_data=Web3.toBytes(lock_periods))
        return receipt

    def _lock_and_create(self, amount: int, lock_periods: int) -> TxReceipt:
        """Public facing method for token locking without depositing."""
        receipt = self.staking_agent.lock_and_create(amount=amount,
                                                     transacting_power=self.transacting_power,
                                                     lock_periods=lock_periods)
        return receipt

    def _divide_stake(self, stake_index: int, additional_periods: int, target_value: int) -> TxReceipt:
        """Public facing method for stake dividing."""
        receipt = self.staking_agent.divide_stake(transacting_power=self.transacting_power,
                                                  stake_index=stake_index,
                                                  target_value=target_value,
                                                  periods=additional_periods)
        return receipt

    def _deposit_and_increase(self, stake_index: int, amount: int) -> TxReceipt:
        """Public facing method for deposit and increasing stake."""
        self._ensure_allowance_equals(amount)
        receipt = self.staking_agent.deposit_and_increase(transacting_power=self.transacting_power,
                                                          stake_index=stake_index,
                                                          amount=amount)
        return receipt

    def _ensure_allowance_equals(self, amount: int):
        owner = self.transacting_power.account
        spender = self.staking_agent.contract.address
        current_allowance = self.token_agent.get_allowance(owner=owner, spender=spender)
        if amount > current_allowance:
            to_increase = amount - current_allowance
            self.token_agent.increase_allowance(increase=to_increase,
                                                transacting_power=self.transacting_power,
                                                spender_address=spender)
            self.log.info(f"{owner} increased token allowance for spender {spender} to {amount}")
        elif amount < current_allowance:
            to_decrease = current_allowance - amount
            self.token_agent.decrease_allowance(decrease=to_decrease,
                                                transacting_power=self.transacting_power,
                                                spender_address=spender)
            self.log.info(f"{owner} decreased token allowance for spender {spender} to {amount}")

    def _lock_and_increase(self, stake_index: int, amount: int) -> TxReceipt:
        """Public facing method for increasing stake."""
        receipt = self.staking_agent.lock_and_increase(transacting_power=self.transacting_power,
                                                       stake_index=stake_index,
                                                       amount=amount)
        return receipt

    def _merge_stakes(self, stake_index_1: int, stake_index_2: int) -> TxReceipt:
        """Public facing method for stakes merging."""
        receipt = self.staking_agent.merge_stakes(stake_index_1=stake_index_1,
                                                  stake_index_2=stake_index_2,
                                                  transacting_power=self.transacting_power)
        return receipt

    @property
    def is_restaking(self) -> bool:
        restaking = self.staking_agent.is_restaking(staker_address=self.checksum_address)
        return restaking

    @only_me
    @save_receipt
    def _set_restaking(self, value: bool) -> TxReceipt:
        receipt = self.staking_agent.set_restaking(transacting_power=self.transacting_power, value=value)
        return receipt

    def enable_restaking(self) -> TxReceipt:
        receipt = self._set_restaking(value=True)
        return receipt

    def disable_restaking(self) -> TxReceipt:
        receipt = self._set_restaking(value=False)
        return receipt

    @property
    def is_winding_down(self) -> bool:
        winding_down = self.staking_agent.is_winding_down(staker_address=self.checksum_address)
        return winding_down

    @only_me
    @save_receipt
    def _set_winding_down(self, value: bool) -> TxReceipt:
        receipt = self.staking_agent.set_winding_down(transacting_power=self.transacting_power, value=value)
        return receipt

    def enable_winding_down(self) -> TxReceipt:
        receipt = self._set_winding_down(value=True)
        return receipt

    def disable_winding_down(self) -> TxReceipt:
        receipt = self._set_winding_down(value=False)
        return receipt

    @property
    def is_taking_snapshots(self) -> bool:
        taking_snapshots = self.staking_agent.is_taking_snapshots(staker_address=self.checksum_address)
        return taking_snapshots

    @only_me
    @save_receipt
    def _set_snapshots(self, value: bool) -> TxReceipt:
        receipt = self.staking_agent.set_snapshots(transacting_power=self.transacting_power, activate=value)
        return receipt

    def enable_snapshots(self) -> TxReceipt:
        receipt = self._set_snapshots(value=True)
        return receipt

    def disable_snapshots(self) -> TxReceipt:
        receipt = self._set_snapshots(value=False)
        return receipt

    @property
    def is_migrated(self) -> bool:
        migrated = self.staking_agent.is_migrated(staker_address=self.checksum_address)
        return migrated

    def migrate(self, staker_address: Optional[ChecksumAddress] = None) -> TxReceipt:
        receipt = self.staking_agent.migrate(transacting_power=self.transacting_power, staker_address=staker_address)
        return receipt

    @only_me
    @save_receipt
    def remove_inactive_stake(self, stake: Stake) -> TxReceipt:
        self._ensure_stake_exists(stake)

        # Read on-chain stake and validate
        stake.sync()
        if not stake.status().is_child(Stake.Status.INACTIVE):
            raise ValueError(f"Stake with index {stake.index} is still active")

        receipt = self._remove_inactive_stake(stake_index=stake.index)

        # Update staking cache element
        self.refresh_stakes()
        return receipt

    @only_me
    @save_receipt
    def _remove_inactive_stake(self, stake_index: int) -> TxReceipt:
        receipt = self.staking_agent.remove_inactive_stake(transacting_power=self.transacting_power,
                                                           stake_index=stake_index)
        return receipt

    def non_withdrawable_stake(self) -> NU:
        staked_amount: NuNits = self.staking_agent.non_withdrawable_stake(staker_address=self.checksum_address)
        return NU.from_nunits(staked_amount)

    @property
    def last_committed_period(self) -> int:
        period = self.staking_agent.get_last_committed_period(staker_address=self.checksum_address)
        return period

    def mintable_periods(self) -> int:
        """
        Returns number of periods that can be rewarded in the current period. Value in range [0, 2]
        """
        current_period: Period = self.staking_agent.get_current_period()
        previous_period: int = current_period - 1
        current_committed_period: Period = self.staking_agent.get_current_committed_period(staker_address=self.checksum_address)
        next_committed_period: Period = self.staking_agent.get_next_committed_period(staker_address=self.checksum_address)

        mintable_periods: int = 0
        if 0 < current_committed_period <= previous_period:
            mintable_periods += 1
        if 0 < next_committed_period <= previous_period:
            mintable_periods += 1

        return mintable_periods

    #
    # Bonding with Worker
    #
    @only_me
    @save_receipt
    @validate_checksum_address
    def bond_worker(self, worker_address: ChecksumAddress) -> TxReceipt:
        receipt = self.staking_agent.bond_worker(transacting_power=self.transacting_power,
                                                 worker_address=worker_address)
        self._worker_address = worker_address
        return receipt

    @property
    def worker_address(self) -> str:
        if not self._worker_address:
            # TODO: This is broken for StakeHolder with different stakers - See #1358
            worker_address = self.staking_agent.get_worker_from_staker(staker_address=self.checksum_address)
            self._worker_address = worker_address

        return self._worker_address

    @only_me
    @save_receipt
    def unbond_worker(self) -> TxReceipt:
        receipt = self.staking_agent.release_worker(transacting_power=self.transacting_power)
        self._worker_address = NULL_ADDRESS
        return receipt

    #
    # Reward and Collection
    #

    @only_me
    @save_receipt
    def mint(self) -> TxReceipt:
        """Computes and transfers tokens to the staker's account"""
        receipt = self.staking_agent.mint(transacting_power=self.transacting_power)
        return receipt

    def calculate_staking_reward(self) -> NU:
        staking_reward = self.staking_agent.calculate_staking_reward(staker_address=self.checksum_address)
        return NU.from_nunits(staking_reward)

    def calculate_policy_fee(self) -> int:
        policy_fee = self.policy_agent.get_fee_amount(staker_address=self.checksum_address)
        return policy_fee

    @only_me
    @save_receipt
    @validate_checksum_address
    def collect_policy_fee(self, collector_address=None) -> TxReceipt:
        """Collect fees (ETH) earned since last withdrawal"""
        withdraw_address = collector_address or self.checksum_address
        receipt = self.policy_agent.collect_policy_fee(collector_address=withdraw_address,
                                                       transacting_power=self.transacting_power)
        return receipt

    @only_me
    @save_receipt
    def collect_staking_reward(self, replace: bool = False) -> TxReceipt:  # TODO: Support replacement for all actor transactions
        """Withdraw tokens rewarded for staking"""
        receipt = self.staking_agent.collect_staking_reward(transacting_power=self.transacting_power, replace=replace)
        return receipt

    @only_me
    @save_receipt
    def withdraw(self, amount: NU, replace: bool = False) -> TxReceipt:
        """Withdraw tokens from StakingEscrow (assuming they're unlocked)"""
        receipt = self.staking_agent.withdraw(transacting_power=self.transacting_power,
                                              amount=NuNits(int(amount)),
                                              replace=replace)
        return receipt

    @property
    def missing_commitments(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_commitments(checksum_address=staker_address)
        return missing

    @only_me
    @save_receipt
    def set_min_fee_rate(self, min_rate: int) -> TxReceipt:
        """Public facing method for staker to set the minimum acceptable fee rate for their associated worker"""
        minimum, _default, maximum = self.policy_agent.get_fee_rate_range()
        if min_rate < minimum or min_rate > maximum:
            raise ValueError(f"Minimum fee rate {min_rate} must fall within global fee range of [{minimum}, {maximum}]")
        receipt = self.policy_agent.set_min_fee_rate(transacting_power=self.transacting_power, min_rate=min_rate)
        return receipt

    @property
    def min_fee_rate(self) -> int:
        """Minimum fee rate that staker accepts"""
        staker_address = self.checksum_address
        min_fee = self.policy_agent.get_min_fee_rate(staker_address)
        return min_fee

    @property
    def raw_min_fee_rate(self) -> int:
        """Minimum acceptable fee rate set by staker for their associated worker.
        This fee rate is only used if it falls within the global fee range.
        If it doesn't a default fee rate is used instead of the raw value (see `min_fee_rate`)"""
        staker_address = self.checksum_address
        min_fee = self.policy_agent.get_raw_min_fee_rate(staker_address)
        return min_fee


class Worker(NucypherTokenActor):
    """
    Ursula baseclass for blockchain operations, practically carrying a pickaxe.
    """

    READY_TIMEOUT = None  # (None or 0) == indefinite
    READY_POLL_RATE = 10
    READY_CLI_FEEDBACK_RATE = 60  # provide feedback to CLI every 60s

    class WorkerError(NucypherTokenActor.ActorError):
        pass

    class UnbondedWorker(WorkerError):
        """Raised when the Worker is not bonded to a Staker in the StakingEscrow contract."""
        crash_right_now = True

    def __init__(self,
                 is_me: bool,
                 work_tracker: WorkTracker = None,
                 worker_address: str = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger("worker")

        self.is_me = is_me

        self.__worker_address = worker_address

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent,
                                                      registry=self.registry)  # type: StakingEscrowAgent

        # Someday, when we have Workers for tasks other than PRE, this might instead be composed on Ursula.
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent,
                                                     registry=self.registry)  # type: PolicyManagerAgent

        # Stakes
        self.__start_time = WORKER_NOT_RUNNING
        self.__uptime_period = WORKER_NOT_RUNNING

        if is_me:
            self.stakes = StakeList(registry=self.registry, checksum_address=self.checksum_address)
            self.work_tracker = work_tracker or WorkTracker(worker=self, stakes=self.stakes)

    def block_until_ready(self, poll_rate: int = None, timeout: int = None, feedback_rate: int = None):
        """
        Polls the staking_agent and blocks until the staking address is not
        a null address for the given worker_address. Once the worker is bonded, it returns the staker address.
        """
        if not self.__worker_address:
            raise RuntimeError("No worker address available")

        timeout = timeout or self.READY_TIMEOUT
        poll_rate = poll_rate or self.READY_POLL_RATE
        feedback_rate = feedback_rate or self.READY_CLI_FEEDBACK_RATE
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        client = staking_agent.blockchain.client
        start = maya.now()
        last_provided_feedback = start

        emitter = StdoutEmitter()

        funded, bonded = False, False
        while True:

            # Read
            staking_address = staking_agent.get_staker_from_worker(self.__worker_address)
            ether_balance = client.get_balance(self.__worker_address)

            # Bonding
            if (not bonded) and (staking_address != NULL_ADDRESS):
                bonded = True
                emitter.message(f"✓ Worker is bonded to {staking_address}", color='green')

            # Balance
            if ether_balance and (not funded):
                funded, balance = True, Web3.fromWei(ether_balance, 'ether')
                emitter.message(f"✓ Worker is funded with {balance} ETH", color='green')

            # Success and Escape
            if staking_address != NULL_ADDRESS and ether_balance:
                self.checksum_address = staking_address
                # TODO: #1823 - Workaround for new nickname every restart
                self.nickname = Nickname.from_seed(self.checksum_address)
                break

            # Provide periodic feedback to the user
            if not bonded or not funded:
                now = maya.now()
                delta = now - last_provided_feedback
                if delta.total_seconds() >= feedback_rate:
                    if not bonded and not funded:
                        waiting_for = "bonding and funding"
                    else:
                        waiting_for = "bonding" if not bonded else "funding"
                    message = f"ⓘ  Worker startup is paused. Waiting for {waiting_for} ..."
                    emitter.message(message, color='blue', bold=True)
                    last_provided_feedback = now

            # Crash on Timeout
            if timeout:
                now = maya.now()
                delta = now - start
                if delta.total_seconds() >= timeout:
                    if staking_address == NULL_ADDRESS:
                        raise self.UnbondedWorker(
                            f"Worker {self.__worker_address} not bonded after waiting {timeout} seconds.")
                    elif not ether_balance:
                        raise RuntimeError(
                            f"Worker {self.__worker_address} has no ETH after waiting {timeout} seconds.")

            # Increment
            time.sleep(poll_rate)

    @property
    def eth_balance(self) -> Decimal:
        """Return this worker's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent #1509
        balance = blockchain.client.get_balance(self.__worker_address)
        return blockchain.client.w3.fromWei(balance, 'ether')

    @property
    def token_balance(self) -> NU:
        """
        Return this worker's current token balance.
        Note: Workers typically do not control any tokens.
        """
        balance = int(self.token_agent.get_balance(address=self.__worker_address))
        nu_balance = NU(balance, 'NuNit')
        return nu_balance

    @property
    def last_committed_period(self) -> int:
        period = self.staking_agent.get_last_committed_period(staker_address=self.checksum_address)
        return period

    @only_me
    @save_receipt  # saves txhash instead of receipt if `fire_and_forget` is True
    def commit_to_next_period(self, fire_and_forget: bool = True) -> Union[TxReceipt, HexBytes]:
        """For each period that the worker makes a commitment, the staker is rewarded"""
        txhash_or_receipt = self.staking_agent.commit_to_next_period(transacting_power=self.transacting_power,
                                                                     fire_and_forget=fire_and_forget)
        return txhash_or_receipt

    @property
    def missing_commitments(self) -> int:
        staker_address = self.checksum_address
        missing = self.staking_agent.get_missing_commitments(checksum_address=staker_address)
        return missing


class BlockchainPolicyAuthor(NucypherTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self,
                 rate: int = None,
                 payment_periods: int = None,
                 *args, **kwargs):
        """
        :param policy_agent: A policy agent with the blockchain attached;
                             If not passed, a default policy agent and blockchain connection will
                             be created from default values.

        """
        super().__init__(*args, **kwargs)

        # From defaults
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)

        self.economics = EconomicsFactory.get_economics(registry=self.registry)
        self.rate = rate
        self.payment_periods = payment_periods

    @property
    def default_rate(self):
        _minimum, default, _maximum = self.policy_agent.get_fee_rate_range()
        return default

    def generate_policy_parameters(self,
                                   number_of_ursulas: int = None,
                                   payment_periods: int = None,
                                   expiration: maya.MayaDT = None,
                                   value: int = None,
                                   rate: int = None,
                                   ) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        if not payment_periods and not expiration:
            raise ValueError("Policy end time must be specified as 'expiration' or 'payment_periods', got neither.")

        # Merge injected and default params.
        rate = rate if rate is not None else self.rate  # TODO conflict with CLI default value, see #1709
        payment_periods = payment_periods or self.payment_periods

        # Calculate duration in periods and expiration datetime
        if payment_periods:
            # Duration equals one period means that expiration date is the last second of the current period
            expiration = datetime_at_period(self.staking_agent.get_current_period() + payment_periods,
                                            seconds_per_period=self.economics.seconds_per_period,
                                            start_of_period=True)
            expiration -= 1  # Get the last second of the target period
        else:
            now = self.staking_agent.blockchain.get_blocktime()
            payment_periods = calculate_period_duration(now=maya.MayaDT(now),
                                                        future_time=expiration,
                                                        seconds_per_period=self.economics.seconds_per_period)
            payment_periods += 1  # Number of all included periods

        from nucypher.policy.policies import BlockchainPolicy
        blockchain_payload = BlockchainPolicy.generate_policy_parameters(n=number_of_ursulas,
                                                                         payment_periods=payment_periods,
                                                                         value=value,
                                                                         rate=rate)

        # These values may have been recalculated in this blocktime.
        policy_end_time = dict(payment_periods=payment_periods, expiration=expiration)
        payload = {**blockchain_payload, **policy_end_time}
        return payload

    def get_stakers_reservoir(self, **options) -> StakersReservoir:
        """
        Get a sampler object containing the currently registered stakers.
        """
        return self.staking_agent.get_stakers_reservoir(**options)

    def create_policy(self, *args, **kwargs):
        """
        Hence the name, a BlockchainPolicyAuthor can create
        a BlockchainPolicy with themself as the author.

        :return: Returns a newly authored BlockchainPolicy with n proposed arrangements.

        """
        from nucypher.policy.policies import BlockchainPolicy
        blockchain_policy = BlockchainPolicy(alice=self, *args, **kwargs)
        return blockchain_policy


class Investigator(NucypherTokenActor):
    """
    Actor that reports incorrect CFrags to the Adjudicator contract.
    In most cases, Bob will act as investigator, but the actor is generic enough than
    anyone can report CFrags.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

    @save_receipt
    def request_evaluation(self, evidence) -> dict:
        receipt = self.adjudicator_agent.evaluate_cfrag(evidence=evidence, transacting_power=self.transacting_power)
        return receipt

    def was_this_evidence_evaluated(self, evidence) -> bool:
        result = self.adjudicator_agent.was_this_evidence_evaluated(evidence=evidence)
        return result


class StakeHolder:
    banner = STAKEHOLDER_BANNER

    class UnknownAccount(KeyError):
        pass

    def __init__(self,
                 signer: Signer,
                 registry: BaseContractRegistry,
                 domain: str,
                 initial_address: str = None,
                 worker_data: dict = None):

        self.worker_data = worker_data
        self.log = Logger(f"stakeholder")
        self.checksum_address = initial_address
        self.registry = registry
        self.domain = domain
        self.staker = None
        self.signer = signer

        if initial_address:
            # If an initial address was passed,
            # it is safe to understand that it has already been used at a higher level.
            if initial_address not in self.signer.accounts:
                message = f"Account {initial_address} is not known by this Ethereum client. Is it a HW account? " \
                          f"If so, make sure that your device is plugged in and you use the --hw-wallet flag."
                raise self.UnknownAccount(message)
            self.assimilate(checksum_address=initial_address)

    @validate_checksum_address
    def assimilate(self, checksum_address: ChecksumAddress, password: str = None) -> None:
        original_form = self.checksum_address
        staking_address = checksum_address
        self.checksum_address = staking_address
        self.staker = self.get_staker(checksum_address=staking_address)
        self.staker.refresh_stakes()
        if password:
            self.signer.unlock_account(account=checksum_address, password=password)
        new_form = self.checksum_address
        self.log.info(f"Setting Staker from {original_form} to {new_form}.")

    @validate_checksum_address
    def get_staker(self, checksum_address: ChecksumAddress):
        if checksum_address not in self.signer.accounts:
            raise ValueError(f"{checksum_address} is not a known client account.")
        transacting_power = TransactingPower(account=checksum_address, signer=self.signer)
        staker = Staker(transacting_power=transacting_power,
                        domain=self.domain,
                        registry=self.registry)
        staker.refresh_stakes()
        return staker

    def get_stakers(self) -> List[Staker]:
        stakers = list()
        for account in self.signer.accounts:
            staker = self.get_staker(checksum_address=account)
            stakers.append(staker)
        return stakers

    @property
    def total_stake(self) -> NU:
        """
        The total number of staked tokens, either locked or unlocked in the current period for all stakers
        controlled by the stakeholder's signer.
        """
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        stake = sum(staking_agent.owned_tokens(staker_address=account) for account in self.signer.accounts)
        nu_stake = NU.from_nunits(stake)
        return nu_stake


class Bidder(NucypherTokenActor):
    """WorkLock participant"""

    class BidderError(NucypherTokenActor.ActorError):
        pass

    class BiddingIsOpen(BidderError):
        pass

    class BiddingIsClosed(BidderError):
        pass

    class CancellationWindowIsOpen(BidderError):
        pass

    class CancellationWindowIsClosed(BidderError):
        pass

    class ClaimError(BidderError):
        pass

    class WhaleError(BidderError):
        pass

    @validate_checksum_address
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = Logger(f"WorkLockBidder")
        self.worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=self.registry)  # type: WorkLockAgent
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)  # type: StakingEscrowAgent
        self.economics = EconomicsFactory.get_economics(registry=self.registry)
        self._all_bonus_bidders = None

    def ensure_bidding_is_open(self, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        start = self.worklock_agent.start_bidding_date
        end = self.worklock_agent.end_bidding_date
        if now < start:
            message = message or f'Bidding does not open until {maya.MayaDT(start).slang_date()}'
            raise self.BiddingIsClosed(message)
        if now >= end:
            message = message or f'Bidding closed at {maya.MayaDT(end).slang_date()}'
            raise self.BiddingIsClosed(message)

    def _ensure_bidding_is_closed(self, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        end = self.worklock_agent.end_bidding_date
        if now < end:
            message = message or f"Bidding does not close until {maya.MayaDT(end).slang_date()}"
            raise self.BiddingIsOpen(message)

    def _ensure_cancellation_window(self, ensure_closed: bool = True, message: str = None) -> None:
        now = self.worklock_agent.blockchain.get_blocktime()
        end = self.worklock_agent.end_cancellation_date
        if ensure_closed and now < end:
            message = message or f"Operation cannot be performed while the cancellation window is still open " \
                                 f"(closes at {maya.MayaDT(end).slang_date()})."
            raise self.CancellationWindowIsOpen(message)
        elif not ensure_closed and now >= end:
            message = message or f"Operation is allowed only while the cancellation window is open " \
                                 f"(closed at {maya.MayaDT(end).slang_date()})."
            raise self.CancellationWindowIsClosed(message)

    #
    # Transactions
    #

    def place_bid(self, value: int) -> TxReceipt:
        self.ensure_bidding_is_open()
        minimum = self.worklock_agent.minimum_allowed_bid
        if not self.get_deposited_eth and value < minimum:
            raise self.BidderError(f"{prettify_eth_amount(value)} is too small a value for bidding; "
                                   f"bid must be at least {prettify_eth_amount(minimum)}")
        receipt = self.worklock_agent.bid(transacting_power=self.transacting_power, value=value)
        return receipt

    def claim(self) -> TxReceipt:

        # Require the cancellation window is closed
        self._ensure_cancellation_window(ensure_closed=True)

        if not self.worklock_agent.is_claiming_available():
            raise self.ClaimError(f"Claiming is not available yet")

        # Ensure the claim was not already placed
        if self.has_claimed:
            raise self.ClaimError(f"Bidder {self.checksum_address} already placed a claim.")

        # Require an active bid
        if not self.get_deposited_eth:
            raise self.ClaimError(f"No bids available for {self.checksum_address}")

        receipt = self.worklock_agent.claim(transacting_power=self.transacting_power)
        return receipt

    def cancel_bid(self) -> TxReceipt:
        self._ensure_cancellation_window(ensure_closed=False)

        # Require an active bid
        if not self.get_deposited_eth:
            self.BidderError(f"No bids available for {self.checksum_address}")

        receipt = self.worklock_agent.cancel_bid(transacting_power=self.transacting_power)
        return receipt

    def _get_max_bonus_bid_from_max_stake(self) -> int:
        """Returns maximum allowed bid calculated from maximum allowed locked tokens"""
        max_bonus_tokens = self.economics.maximum_allowed_locked - self.economics.minimum_allowed_locked
        bonus_eth_supply = sum(
            self._all_bonus_bidders.values()) if self._all_bonus_bidders else self.worklock_agent.get_bonus_eth_supply()
        bonus_worklock_supply = self.worklock_agent.get_bonus_lot_value()
        max_bonus_bid = max_bonus_tokens * bonus_eth_supply // bonus_worklock_supply
        return max_bonus_bid

    def get_whales(self, force_read: bool = False) -> Dict[str, int]:
        """Returns all worklock bidders over the whale threshold as a dictionary of addresses and bonus bid values."""
        max_bonus_bid_from_max_stake = self._get_max_bonus_bid_from_max_stake()

        bidders = dict()
        for bidder, bid in self._get_all_bonus_bidders(force_read).items():
            if bid > max_bonus_bid_from_max_stake:
                bidders[bidder] = bid
        return bidders

    def _get_all_bonus_bidders(self, force_read: bool = False) -> dict:
        if not force_read and self._all_bonus_bidders:
            return self._all_bonus_bidders

        bidders = self.worklock_agent.get_bidders()
        min_bid = self.economics.worklock_min_allowed_bid

        self._all_bonus_bidders = dict()
        for bidder in bidders:
            bid = self.worklock_agent.get_deposited_eth(bidder)
            if bid > min_bid:
                self._all_bonus_bidders[bidder] = bid - min_bid
        return self._all_bonus_bidders

    def _reduce_bids(self, whales: dict):

        min_whale_bonus_bid = min(whales.values())
        max_whale_bonus_bid = max(whales.values())

        # first step - align at a minimum bid
        if min_whale_bonus_bid != max_whale_bonus_bid:
            whales = dict.fromkeys(whales.keys(), min_whale_bonus_bid)
            self._all_bonus_bidders.update(whales)

        bonus_eth_supply = sum(self._all_bonus_bidders.values())
        bonus_worklock_supply = self.worklock_agent.get_bonus_lot_value()
        max_bonus_tokens = self.economics.maximum_allowed_locked - self.economics.minimum_allowed_locked
        if (min_whale_bonus_bid * bonus_worklock_supply) // bonus_eth_supply <= max_bonus_tokens:
            raise self.WhaleError(f"At least one of bidders {whales} has allowable bid")

        a = min_whale_bonus_bid * bonus_worklock_supply - max_bonus_tokens * bonus_eth_supply
        b = bonus_worklock_supply - max_bonus_tokens * len(whales)
        refund = -(-a // b)  # div ceil
        min_whale_bonus_bid -= refund
        whales = dict.fromkeys(whales.keys(), min_whale_bonus_bid)
        self._all_bonus_bidders.update(whales)

        return whales

    def force_refund(self) -> TxReceipt:
        self._ensure_cancellation_window(ensure_closed=True)

        whales = self.get_whales()
        if not whales:
            raise self.WhaleError(f"Force refund aborted: No whales detected and all bids qualify for claims.")

        new_whales = whales.copy()
        while new_whales:
            whales.update(new_whales)
            whales = self._reduce_bids(whales)
            new_whales = self.get_whales()

        receipt = self.worklock_agent.force_refund(transacting_power=self.transacting_power,
                                                   addresses=list(whales.keys()))

        if self.get_whales(force_read=True):
            raise RuntimeError(f"Internal error: offline simulation differs from transaction results")
        return receipt

    # TODO better control: max iterations, interactive mode
    def verify_bidding_correctness(self, gas_limit: int) -> dict:
        self._ensure_cancellation_window(ensure_closed=True)

        if self.worklock_agent.bidders_checked():
            raise self.BidderError(f"Check was already done")

        whales = self.get_whales()
        if whales:
            raise self.WhaleError(f"Some bidders have bids that are too high: {whales}")

        self.log.debug(f"Starting bidding verification. Next bidder to check: {self.worklock_agent.next_bidder_to_check()}")

        receipts = dict()
        iteration = 1
        while not self.worklock_agent.bidders_checked():
            receipt = self.worklock_agent.verify_bidding_correctness(transacting_power=self.transacting_power,
                                                                     gas_limit=gas_limit)
            self.log.debug(f"Iteration {iteration}. Next bidder to check: {self.worklock_agent.next_bidder_to_check()}")
            receipts[iteration] = receipt
            iteration += 1
        return receipts

    def refund_deposit(self) -> dict:
        """Refund ethers for completed work"""
        if not self.available_refund:
            raise self.BidderError(f'There is no refund available for {self.checksum_address}')
        receipt = self.worklock_agent.refund(transacting_power=self.transacting_power)
        return receipt

    def withdraw_compensation(self) -> TxReceipt:
        """Withdraw compensation after force refund"""
        if not self.available_compensation:
            raise self.BidderError(f'There is no compensation available for {self.checksum_address}; '
                                   f'Did you mean to call "refund"?')
        receipt = self.worklock_agent.withdraw_compensation(transacting_power=self.transacting_power)
        return receipt

    #
    # Calls
    #

    @property
    def get_deposited_eth(self) -> int:
        bid = self.worklock_agent.get_deposited_eth(checksum_address=self.checksum_address)
        return bid

    @property
    def has_claimed(self) -> bool:
        has_claimed = self.worklock_agent.check_claim(self.checksum_address)
        return has_claimed

    @property
    def completed_work(self) -> int:
        work = self.staking_agent.get_completed_work(bidder_address=self.checksum_address)
        completed_work = work - self.refunded_work
        return completed_work

    @property
    def remaining_work(self) -> int:
        try:
            work = self.worklock_agent.get_remaining_work(checksum_address=self.checksum_address)
        except (TestTransactionFailed, ValidationError, ValueError):  # TODO: 1950
            work = 0
        return work

    @property
    def refunded_work(self) -> int:
        work = self.worklock_agent.get_refunded_work(checksum_address=self.checksum_address)
        return work

    @property
    def available_refund(self) -> int:
        refund_eth = self.worklock_agent.get_available_refund(checksum_address=self.checksum_address)
        return refund_eth

    @property
    def available_compensation(self) -> int:
        compensation_eth = self.worklock_agent.get_available_compensation(checksum_address=self.checksum_address)
        return compensation_eth

    @property
    def available_claim(self) -> int:
        tokens = self.worklock_agent.eth_to_tokens(self.get_deposited_eth)
        return tokens


class DaoActor(BaseActor):
    """Generic actor to interact with the NuCypher DAO"""

    def __init__(self,
                 network: str,
                 checksum_address: ChecksumAddress,
                 registry=None,
                 signer: Signer = None,
                 transacting: bool = True):
        super().__init__(registry=registry, domain=network, checksum_address=checksum_address)
        self.dao_registry = DAORegistry(network=network)
        if transacting:  # TODO: This logic is repeated in Bidder and possible others.
            self.transacting_power = TransactingPower(signer=signer, account=checksum_address)

        self.aragon_agent = AragonAgent(self.dao_registry.get_address_of(DAO_AGENT))
        self.token_manager = TokenManagerAgent(address=self.dao_registry.get_address_of(EMERGENCY_MANAGER))
        self.voting = VotingAgent(address=self.dao_registry.get_address_of(STANDARD_VOTING))
        self.voting_aggregator = VotingAggregatorAgent(self.dao_registry.get_address_of(STANDARD_AGGREGATOR))

    def rotate_emergency_response_team(self,
                                       members_out: Iterable[ChecksumAddress],
                                       members_in: Iterable[ChecksumAddress]) -> TxReceipt:

        members_out_set = set(members_out)
        if not members_out_set.isdisjoint(members_in):
            raise ValueError(f"{members_out_set.intersection(members_in)} can't be both new and exiting members")

        # TODO: Additional checks? e.g., members_out have tokens, members_in don't, etc.

        # The order of interaction is: Voter -> VotingAggregator -> VotingApp -> TokenManager
        # Hence, the callscript is encoded in the reverse order: TokenManager > VotingApp > VotingAggregator

        burn_calls = [self.token_manager._burn(holder_address=member, amount=1) for member in members_out]
        mint_calls = [self.token_manager._mint(receiver_address=member, amount=1) for member in members_in]
        calls = burn_calls + mint_calls

        actions = [Action(target=self.token_manager.contract.address, data=call) for call in calls]
        token_manager_callscript = CallScriptCodec.encode_actions(actions=actions)

        forwarding_to_voting = Action(target=self.voting.contract.address,
                                      data=self.voting._forward(callscript=token_manager_callscript))
        voting_callscript = CallScriptCodec.encode_actions(actions=[forwarding_to_voting])

        receipt = self.voting_aggregator.forward(callscript=voting_callscript, transacting_power=self.transacting_power)
        return receipt

    def period_extension_proposal(self,
                                  policy_manager_target: ChecksumAddress,
                                  staking_escrow_target: ChecksumAddress) -> TxReceipt:

        # The order of interaction is: Voter -> VotingAggregator -> VotingApp -> AragonAgent -> NU Contracts
        # The callscript is encoded in the reverse order: NU Contracts > AragonAgent > VotingApp > VotingAggregator

        blockchain = BlockchainInterfaceFactory.get_interface()

        policy_manager_implementation = blockchain.get_contract_by_name(registry=self.registry,
                                                                        contract_name=POLICY_MANAGER_CONTRACT_NAME,
                                                                        proxy_name=DISPATCHER_CONTRACT_NAME,
                                                                        use_proxy_address=False)
        staking_escrow_implementation = blockchain.get_contract_by_name(registry=self.registry,
                                                                        contract_name=STAKING_ESCROW_CONTRACT_NAME,
                                                                        proxy_name=DISPATCHER_CONTRACT_NAME,
                                                                        use_proxy_address=False)

        policy_manager_dispatcher = blockchain.get_proxy_contract(registry=self.registry,
                                                                  target_address=policy_manager_implementation.address,
                                                                  proxy_name=DISPATCHER_CONTRACT_NAME)

        staking_escrow_dispatcher = blockchain.get_proxy_contract(registry=self.registry,
                                                                  target_address=staking_escrow_implementation.address,
                                                                  proxy_name=DISPATCHER_CONTRACT_NAME)

        policy_manager_upgrade = policy_manager_dispatcher.functions.upgrade(policy_manager_target)
        staking_escrow_upgrade = staking_escrow_dispatcher.functions.upgrade(staking_escrow_target)

        # FIXME: Get new parameters for fee rate range

        minimum = Web3.toWei(350, 'gwei')
        default = minimum
        maximum = Web3.toWei(3500, 'gwei')

        set_range = policy_manager_implementation.functions.setFeeRateRange(minimum, default, maximum)

        def call_to_bytes(function_call) -> bytes:
            encoded_action = function_call._encode_transaction_data()
            action_bytes = Web3.toBytes(hexstr=encoded_action)
            return action_bytes

        execution_list = (
            (staking_escrow_dispatcher.address, staking_escrow_upgrade),
            (policy_manager_dispatcher.address, policy_manager_upgrade),
            (policy_manager_dispatcher.address, set_range),
        )

        actions = []
        for target, data in execution_list:
            action = self.aragon_agent.get_execute_call_as_action(target_address=target, data=call_to_bytes(data))
            actions.append(action)

        agent_executions_callscript = CallScriptCodec.encode_actions(actions=actions)

        voting_callscript = Action(target=self.voting.contract.address,
                                   data=self.voting._forward(callscript=agent_executions_callscript))
        aggregator_callscript = CallScriptCodec.encode_actions(actions=[voting_callscript])

        receipt = self.voting_aggregator.forward(callscript=aggregator_callscript,
                                                 transacting_power=self.transacting_power)
        return receipt

# TODO:
# - Tests for DAO stuff requires mocking the DAO. We need stuff like MockTokenManager, MockVoting, etc
