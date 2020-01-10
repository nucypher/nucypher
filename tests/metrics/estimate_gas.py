#!/usr/bin/env python3


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
import sys

import io
import re
import time
from os.path import abspath, dirname
from unittest.mock import Mock

from twisted.logger import globalLogPublisher, Logger, jsonFileLogObserver, ILogObserver
from zope.interface import provider

from nucypher.blockchain.economics import StandardTokenEconomics
from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, PolicyManagerAgent, AdjudicatorAgent
from nucypher.crypto.signing import SignatureStamp
from nucypher.policy.policies import Policy
from nucypher.utilities.sandbox.blockchain import TesterBlockchain
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

# FIXME: Needed to use a fixture here, but now estimate_gas.py only runs if executed from main directory
sys.path.insert(0, abspath('tests'))
from fixtures import _mock_ursula_reencrypts as mock_ursula_reencrypts


ALGORITHM_SHA256 = 1
TOKEN_ECONOMICS = StandardTokenEconomics()
MIN_ALLOWED_LOCKED = TOKEN_ECONOMICS.minimum_allowed_locked
MIN_LOCKED_PERIODS = TOKEN_ECONOMICS.minimum_locked_periods
MAX_ALLOWED_LOCKED = TOKEN_ECONOMICS.maximum_allowed_locked
MAX_MINTING_PERIODS = TOKEN_ECONOMICS.maximum_rewarded_periods


class AnalyzeGas:
    """
    Callable twisted log observer with built-in record-keeping for gas estimation runs.
    """

    # Logging
    LOG_NAME = 'estimate-gas'
    LOG_FILENAME = '{}.log.json'.format(LOG_NAME)
    OUTPUT_DIR = os.path.join(abspath(dirname(__file__)), 'results')
    JSON_OUTPUT_FILENAME = '{}.json'.format(LOG_NAME)

    _PATTERN = re.compile(r'''
                          ^          # Anchor at the start of a string
                          (.+)       # Any character sequence longer than 1; Captured
                          \s=\s      # Space-Equal-Space
                          (\d+)      # A sequence of digits; Captured
                          \|
                          (\d+)      # A sequence of digits; Captured
                          $          # Anchor at the end of the string
                          ''', re.VERBOSE)

    def __init__(self) -> None:

        self.log = Logger(self.__class__.__name__)
        self.gas_estimations = dict()

        if not os.path.isdir(self.OUTPUT_DIR):
            os.mkdir(self.OUTPUT_DIR)

    @provider(ILogObserver)
    def __call__(self, event, *args, **kwargs) -> None:

        if event.get('log_namespace') == self.LOG_NAME:
            message = event.get("log_format")

            matches = self._PATTERN.match(message)
            if not matches:
                self.log.debug("No match for {} with pattern {}".format(message, self._PATTERN))
                return

            label, estimates, gas_used = matches.groups()
            self.paint_line(label, estimates, gas_used)
            self.gas_estimations[label] = int(gas_used)

    @staticmethod
    def paint_line(label: str, estimates: str, gas_used: str) -> None:
        print('{label} {estimates:7,}|{gas:7,}'.format(
            label=label.ljust(70, '.'), estimates=int(estimates), gas=int(gas_used)))

    def to_json_file(self) -> None:
        print('Saving JSON Output...')

        epoch_time = str(int(time.time()))
        timestamped_filename = '{}-{}'.format(epoch_time, self.JSON_OUTPUT_FILENAME)
        filepath = os.path.join(self.OUTPUT_DIR, timestamped_filename)
        with open(filepath, 'w') as file:
            file.write(json.dumps(self.gas_estimations, indent=4))

    def start_collection(self) -> None:
        print("Starting Data Collection...")

        json_filepath = os.path.join(self.OUTPUT_DIR, AnalyzeGas.LOG_FILENAME)
        json_io = io.open(json_filepath, "w")
        json_observer = jsonFileLogObserver(json_io)
        globalLogPublisher.addObserver(json_observer)
        globalLogPublisher.addObserver(self)


def mock_ursula(testerchain, account):
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


def generate_args_for_slashing(ursula, corrupt_cfrag: bool = True):
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=corrupt_cfrag)
    args = list(evidence.evaluation_arguments())
    return args


def estimate_gas(analyzer: AnalyzeGas = None) -> None:
    """
    Execute a linear sequence of NyCypher transactions mimicking
    post-deployment usage on a local PyEVM blockchain;
    Record the resulting estimated transaction gas expenditure.

    Note: The function calls below are *order dependant*
    """

    #
    # Setup
    #

    if analyzer is None:
        analyzer = AnalyzeGas()

    log = Logger(AnalyzeGas.LOG_NAME)
    os.environ['GAS_ESTIMATOR_BACKEND_FUNC'] = 'eth.estimators.gas.binary_gas_search_exact'

    # Blockchain
    economics = StandardTokenEconomics(
        base_penalty=MIN_ALLOWED_LOCKED - 1,
        penalty_history_coefficient=0,
        percentage_penalty_coefficient=2,
        reward_coefficient=2
    )
    testerchain, registry = TesterBlockchain.bootstrap_network(economics=economics)
    web3 = testerchain.w3

    # Accounts
    origin, ursula1, ursula2, ursula3, alice1, alice2, *everyone_else = testerchain.client.accounts

    ursula_with_stamp = mock_ursula(testerchain, ursula1)

    # Contracts
    token_agent = NucypherTokenAgent(registry=registry)
    staking_agent = StakingEscrowAgent(registry=registry)
    policy_agent = PolicyManagerAgent(registry=registry)
    adjudicator_agent = AdjudicatorAgent(registry=registry)

    # Contract Callers
    token_functions = token_agent.contract.functions
    staker_functions = staking_agent.contract.functions
    policy_functions = policy_agent.contract.functions
    adjudicator_functions = adjudicator_agent.contract.functions

    analyzer.start_collection()
    print("********* Estimating Gas *********")

    def transact_and_log(label, function, transaction):
        estimates = function.estimateGas(transaction)
        transaction.update(gas=estimates)
        tx = function.transact(transaction)
        receipt = testerchain.wait_for_receipt(tx)
        log.info(f"{label} = {estimates}|{receipt['gasUsed']}")

    def transact(function, transaction):
        transaction.update(gas=1000000)
        tx = function.transact(transaction)
        testerchain.wait_for_receipt(tx)

        #
    # Give Ursula and Alice some coins
    #
    transact_and_log("Transfer tokens", token_functions.transfer(ursula1, MIN_ALLOWED_LOCKED * 10), {'from': origin})
    transact(token_functions.transfer(ursula2, MIN_ALLOWED_LOCKED * 10), {'from': origin})
    transact(token_functions.transfer(ursula3, MIN_ALLOWED_LOCKED * 10), {'from': origin})

    #
    # Ursula and Alice give Escrow rights to transfer
    #
    transact_and_log("Approving transfer",
                     token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6),
                     {'from': ursula1})
    transact(token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6), {'from': ursula2})
    transact(token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6), {'from': ursula3})

    #
    # Ursula and Alice transfer some tokens to the escrow and lock them
    #
    transact_and_log("Initial deposit tokens, 1st",
                     staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS),
                     {'from': ursula1})
    transact_and_log("Initial deposit tokens, 2nd",
                     staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS),
                     {'from': ursula2})
    transact(staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS), {'from': ursula3})

    transact(staker_functions.setWorker(ursula1), {'from': ursula1})
    transact(staker_functions.setWorker(ursula2), {'from': ursula2})
    transact(staker_functions.setWorker(ursula3), {'from': ursula3})
    transact(staker_functions.setReStake(False), {'from': ursula1})
    transact(staker_functions.setReStake(False), {'from': ursula2})
    transact(staker_functions.confirmActivity(), {'from': ursula1})
    transact(staker_functions.confirmActivity(), {'from': ursula2})

    #
    # Wait 1 period and confirm activity
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Confirm activity, 1st", staker_functions.confirmActivity(), {'from': ursula1})
    transact_and_log("Confirm activity, 2nd", staker_functions.confirmActivity(), {'from': ursula2})

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Mining (1 stake), 1st", staker_functions.mint(), {'from': ursula1})
    transact_and_log("Mining (1 stake), 2nd", staker_functions.mint(), {'from': ursula2})
    transact_and_log("Confirm activity again, 1st", staker_functions.confirmActivity(), {'from': ursula1})
    transact_and_log("Confirm activity again, 2nd", staker_functions.confirmActivity(), {'from': ursula2})

    #
    # Confirm again
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Confirm activity + mint, 1st", staker_functions.confirmActivity(), {'from': ursula1})
    transact_and_log("Confirm activity + mint, 2nd", staker_functions.confirmActivity(), {'from': ursula2})

    #
    # Get locked tokens
    #
    transact_and_log("Getting locked tokens", staker_functions.getLockedTokens(ursula1, 0), {})

    #
    # Wait 1 period and withdraw tokens
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Withdraw", staker_functions.withdraw(1), {'from': ursula1})

    #
    # Confirm activity with re-stake
    #
    transact(staker_functions.setReStake(True), {'from': ursula1})
    transact(staker_functions.setReStake(True), {'from': ursula2})

    transact_and_log("Confirm activity + mint with re-stake, 1st",
                     staker_functions.confirmActivity(),
                     {'from': ursula1})
    transact_and_log("Confirm activity + mint with re-stake, 2nd",
                     staker_functions.confirmActivity(),
                     {'from': ursula2})

    transact(staker_functions.setReStake(False), {'from': ursula1})
    transact(staker_functions.setReStake(False), {'from': ursula2})

    #
    # Wait 1 period
    #
    testerchain.time_travel(periods=1)

    #
    # Create policy
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 10
    rate = 100
    one_period = economics.hours_per_period * 60 * 60
    value = number_of_periods * rate
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    transact_and_log("Creating policy (1 node, 10 periods, pre-confirmed), 1st",
                     policy_functions.createPolicy(policy_id_1, alice1, end_timestamp, [ursula1]),
                     {'from': alice1, 'value': value})
    transact_and_log("Creating policy (1 node, 10 periods, pre-confirmed), 2nd",
                     policy_functions.createPolicy(policy_id_2, alice1, end_timestamp, [ursula1]),
                     {'from': alice1, 'value': value})

    #
    # Wait 2 periods and confirm activity after downtime
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Confirm activity after downtime, 1st", staker_functions.confirmActivity(), {'from': ursula1})
    transact_and_log("Confirm activity after downtime, 2nd", staker_functions.confirmActivity(), {'from': ursula2})
    transact(staker_functions.confirmActivity(), {'from': ursula3})

    #
    # Ursula and Alice deposit some tokens to the escrow again
    #
    transact_and_log("Deposit tokens after confirming activity",
                     staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS),
                     {'from': ursula1})
    transact(staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS), {'from': ursula2})

    #
    # Revoke policy
    #
    transact_and_log("Revoking policy", policy_functions.revokePolicy(policy_id_1), {'from': alice1})

    #
    # Wait 1 period
    #
    testerchain.time_travel(periods=1)

    #
    # Create policy with multiple pre-confirmed nodes
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 100
    value = 3 * number_of_periods * rate
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    transact_and_log("Creating policy (3 nodes, 100 periods, pre-confirmed), 1st",
                     policy_functions.createPolicy(policy_id_1, alice1, end_timestamp, [ursula1, ursula2, ursula3]),
                     {'from': alice1, 'value': value})
    transact_and_log("Creating policy (3 nodes, 100 periods, pre-confirmed), 2nd",
                     policy_functions.createPolicy(policy_id_2, alice1, end_timestamp, [ursula1, ursula2, ursula3]),
                     {'from': alice1, 'value': value})
    value = 2 * number_of_periods * rate
    transact_and_log("Creating policy (2 nodes, 100 periods, pre-confirmed), 3rd",
                     policy_functions.createPolicy(policy_id_3, alice1, end_timestamp, [ursula1, ursula2]),
                     {'from': alice1, 'value': value})

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    transact_and_log("Mining with updating reward, 1st", staker_functions.mint(), {'from': ursula1})
    transact_and_log("Mining with updating reward, 2nd", staker_functions.mint(), {'from': ursula2})

    #
    # Create policy again without pre-confirmed nodes
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 100
    value = number_of_periods * rate
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    transact_and_log("Creating policy (1 node, 100 periods), 1st",
                     policy_functions.createPolicy(policy_id_1, alice2, end_timestamp, [ursula2]),
                     {'from': alice1, 'value': value})
    testerchain.time_travel(periods=1)
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    transact_and_log("Creating policy (1 node, 100 periods), 2nd",
                     policy_functions.createPolicy(policy_id_2, alice2, end_timestamp, [ursula2]),
                     {'from': alice1, 'value': value})
    transact_and_log("Creating policy (1 node, 100 periods), 3rd",
                     policy_functions.createPolicy(policy_id_3, alice2, end_timestamp, [ursula1]),
                     {'from': alice1, 'value': value})

    #
    # Mine and revoke policy
    #
    testerchain.time_travel(periods=10)
    transact(staker_functions.confirmActivity(), {'from': ursula1})

    testerchain.time_travel(periods=2)
    transact_and_log("Mining after downtime", staker_functions.mint(), {'from': ursula1})

    testerchain.time_travel(periods=10)
    transact_and_log("Revoking policy after downtime, 1st",
                     policy_functions.revokePolicy(policy_id_1),
                     {'from': alice2})
    transact_and_log("Revoking policy after downtime, 2nd",
                     policy_functions.revokePolicy(policy_id_2),
                     {'from': alice2})
    transact_and_log("Revoking policy after downtime, 3rd",
                     policy_functions.revokePolicy(policy_id_3),
                     {'from': alice2})

    for index in range(5):
        transact(staker_functions.confirmActivity(), {'from': ursula1})
        testerchain.time_travel(periods=1)
    transact(staker_functions.mint(), {'from': ursula1})

    #
    # Check regular deposit
    #
    transact_and_log("Deposit tokens",
                     staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS),
                     {'from': ursula1})

    #
    # ApproveAndCall
    #
    testerchain.time_travel(periods=1)
    transact(staker_functions.mint(), {'from': ursula1})

    transact_and_log("ApproveAndCall",
                     token_functions.approveAndCall(staking_agent.contract_address,
                                                    MIN_ALLOWED_LOCKED * 2,
                                                    web3.toBytes(MIN_LOCKED_PERIODS)),
                     {'from': ursula1})

    #
    # Locking tokens
    #
    testerchain.time_travel(periods=1)
    transact(staker_functions.confirmActivity(), {'from': ursula1})
    transact_and_log("Locking tokens", staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS), {'from': ursula1})

    #
    # Divide stake
    #
    transact_and_log("Divide stake", staker_functions.divideStake(1, MIN_ALLOWED_LOCKED, 2), {'from': ursula1})
    transact(staker_functions.divideStake(3, MIN_ALLOWED_LOCKED, 2), {'from': ursula1})

    #
    # Divide almost finished stake
    #
    testerchain.time_travel(periods=1)
    transact(staker_functions.confirmActivity(), {'from': ursula1})
    testerchain.time_travel(periods=1)
    transact(staker_functions.confirmActivity(), {'from': ursula1})

    #
    # Slashing tests
    #
    transact(staker_functions.confirmActivity(), {'from': ursula1})
    testerchain.time_travel(periods=1)

    #
    # Slashing
    #
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slash just value", adjudicator_functions.evaluateCFrag(*slashing_args), {'from': alice1})

    deposit = staker_functions.stakerInfo(ursula1).call()[0]
    unlocked = deposit - staker_functions.getLockedTokens(ursula1, 0).call()
    transact(staker_functions.withdraw(unlocked), {'from': ursula1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes), 1st",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes), 2nd",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes), 3rd",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing two sub stakes and saving old one (" + sub_stakes_length + " sub stakes)",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    for index in range(18):
        transact(staker_functions.confirmActivity(), {'from': ursula1})
        testerchain.time_travel(periods=1)

    transact(staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS), {'from': ursula1})
    deposit = staker_functions.stakerInfo(ursula1).call()[0]
    unlocked = deposit - staker_functions.getLockedTokens(ursula1, 1).call()
    transact(staker_functions.withdraw(unlocked), {'from': ursula1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing two sub stakes, shortest and new one (" + sub_stakes_length + " sub stakes)",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(ursula_with_stamp)
    transact_and_log("Slashing three sub stakes, two shortest and new one (" + sub_stakes_length + " sub stakes)",
                     adjudicator_functions.evaluateCFrag(*slashing_args),
                     {'from': alice1})

    slashing_args = generate_args_for_slashing(ursula_with_stamp, corrupt_cfrag=False)
    transact_and_log("Evaluating correct CFrag", adjudicator_functions.evaluateCFrag(*slashing_args), {'from': alice1})

    transact_and_log("Prolong stake", staker_functions.prolongStake(0, 20), {'from': ursula1})

    print("********* All Done! *********")


if __name__ == "__main__":
    print("Starting Up...")
    analyzer = AnalyzeGas()
    estimate_gas(analyzer=analyzer)
    analyzer.to_json_file()
