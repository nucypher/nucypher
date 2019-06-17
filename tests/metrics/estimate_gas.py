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

import io
import json
import os
import re
import sys
import time
from mock import Mock
from os.path import abspath, dirname

from eth_utils import to_canonical_address
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from twisted.logger import globalLogPublisher, Logger, jsonFileLogObserver, ILogObserver
from zope.interface import provider

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, PolicyAgent, AdjudicatorAgent
from nucypher.crypto.signing import SignatureStamp
from nucypher.crypto.utils import get_coordinates_as_bytes
from nucypher.policy.models import Policy
from nucypher.utilities.sandbox.blockchain import TesterBlockchain

# FIXME: Needed to use a fixture here, but now estimate_gas.py only runs if executed from main directory
sys.path.insert(0, abspath('tests'))
from fixtures import _mock_ursula_reencrypts as mock_ursula_reencrypts


ALGORITHM_SHA256 = 1
TOKEN_ECONOMICS = TokenEconomics()
MIN_ALLOWED_LOCKED = TOKEN_ECONOMICS.minimum_allowed_locked
MIN_LOCKED_PERIODS = TOKEN_ECONOMICS.minimum_locked_periods
MAX_ALLOWED_LOCKED = TOKEN_ECONOMICS.maximum_allowed_locked
MAX_MINTING_PERIODS = TOKEN_ECONOMICS.maximum_locked_periods


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

            label, gas = matches.groups()
            self.paint_line(label, gas)
            self.gas_estimations[label] = int(gas)

    @staticmethod
    def paint_line(label: str, gas: str) -> None:
        print('{label} {gas:,}'.format(label=label.ljust(70, '.'), gas=int(gas)))

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


def mock_ursula_with_stamp():
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))
    ursula = Mock(stamp=ursula_stamp)
    return ursula


def sha256_hash(data):
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(data)
    digest = hash_ctx.finalize()
    return digest


def generate_args_for_slashing(testerchain, ursula, account, corrupt_cfrag: bool = True):
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=corrupt_cfrag)

    # Sign Umbral public key using eth-key
    staker_umbral_public_key_hash = sha256_hash(get_coordinates_as_bytes(ursula.stamp))
    provider = testerchain.provider
    address = to_canonical_address(account)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_staker_umbral_public_key = bytes(sig_key.sign_msg_hash(staker_umbral_public_key_hash))

    args = list(evidence.evaluation_arguments())
    args[-2] = signed_staker_umbral_public_key  # FIXME  #962
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

    # Blockchain
    testerchain, agents = TesterBlockchain.bootstrap_network()
    web3 = testerchain.w3

    # Accounts
    origin, ursula1, ursula2, ursula3, alice1, *everyone_else = testerchain.w3.eth.accounts

    ursula_with_stamp = mock_ursula_with_stamp()

    # Contracts
    token_agent = NucypherTokenAgent(blockchain=testerchain)
    staking_agent = StakingEscrowAgent(blockchain=testerchain)
    policy_agent = PolicyAgent(blockchain=testerchain)
    adjudicator_agent = AdjudicatorAgent()

    # Contract Callers
    token_functions = token_agent.contract.functions
    staker_functions = staking_agent.contract.functions
    policy_functions = policy_agent.contract.functions
    adjudicator_functions = adjudicator_agent.contract.functions

    analyzer.start_collection()
    print("********* Estimating Gas *********")

    #
    # Pre deposit tokens
    #
    tx = token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 5).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    log.info("Pre-deposit tokens for 5 owners = " + str(staker_functions.preDeposit(everyone_else[0:5],
                                                                                   [MIN_ALLOWED_LOCKED] * 5,
                                                                                   [MIN_LOCKED_PERIODS] * 5)
                                                        .estimateGas({'from': origin})))

    #
    # Give Ursula and Alice some coins
    #
    log.info("Transfer tokens = " + str(
        token_functions.transfer(ursula1, MIN_ALLOWED_LOCKED * 10).estimateGas({'from': origin})))
    tx = token_functions.transfer(ursula1, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.transfer(ursula2, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.transfer(ursula3, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)

    #
    # Ursula and Alice give Escrow rights to transfer
    #
    log.info("Approving transfer = "
             + str(
        token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6).estimateGas({'from': ursula1})))
    tx = token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.approve(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Ursula and Alice transfer some tokens to the escrow and lock them
    #
    log.info("First initial deposit tokens = " + str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second initial deposit tokens = " +
             str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third initial deposit tokens = " +
             str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    tx = staker_functions.setWorker(ursula1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setWorker(ursula3).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and confirm activity
    #
    testerchain.time_travel(periods=1)
    log.info("First confirm activity = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First mining (1 stake) = " + str(staker_functions.mint().estimateGas({'from': ursula1})))
    tx = staker_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining (1 stake) = " + str(staker_functions.mint().estimateGas({'from': ursula2})))
    tx = staker_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining (1 stake) = " + str(staker_functions.mint().estimateGas({'from': ursula3})))
    tx = staker_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First confirm activity again = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity again = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity again = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Confirm again
    #
    testerchain.time_travel(periods=1)
    log.info("First confirm activity + mint = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity + mint = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity + mint = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Get locked tokens
    #
    log.info("Getting locked tokens = " + str(staker_functions.getLockedTokens(ursula1).estimateGas()))

    #
    # Wait 1 period and withdraw tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First withdraw = " + str(staker_functions.withdraw(1).estimateGas({'from': ursula1})))
    tx = staker_functions.withdraw(1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second withdraw = " + str(staker_functions.withdraw(1).estimateGas({'from': ursula2})))
    tx = staker_functions.withdraw(1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third withdraw = " + str(staker_functions.withdraw(1).estimateGas({'from': ursula3})))
    tx = staker_functions.withdraw(1).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Confirm activity with re-stake
    #
    tx = staker_functions.setReStake(True).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setReStake(True).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setReStake(True).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First confirm activity + mint with re-stake = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity + mint with re-stake  = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity + mint with re-stake  = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    tx = staker_functions.setReStake(False).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setReStake(False).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.setReStake(False).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 2 periods and confirm activity after downtime
    #
    testerchain.time_travel(periods=2)
    log.info("First confirm activity after downtime = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity after downtime  = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity after downtime  = " +
             str(staker_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Ursula and Alice deposit some tokens to the escrow again
    #
    log.info("First deposit tokens again = " +
             str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens again = " +
             str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens again = " +
             str(staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First mining again = " + str(staker_functions.mint().estimateGas({'from': ursula1})))
    tx = staker_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining again = " + str(staker_functions.mint().estimateGas({'from': ursula2})))
    tx = staker_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining again = " + str(staker_functions.mint().estimateGas({'from': ursula3})))
    tx = staker_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Create policy
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 10
    log.info("First creating policy (1 node, 10 periods) = " +
             str(policy_functions.createPolicy(policy_id_1, number_of_periods, 0, [ursula1]).estimateGas(
                 {'from': alice1, 'value': 10000})))
    tx = policy_functions.createPolicy(policy_id_1, number_of_periods, 0, [ursula1]).transact(
        {'from': alice1, 'value': 10000})
    testerchain.wait_for_receipt(tx)
    log.info("Second creating policy (1 node, 10 periods) = " +
             str(policy_functions.createPolicy(policy_id_2, number_of_periods, 0, [ursula1]).estimateGas(
                 {'from': alice1, 'value': 10000})))
    tx = policy_functions.createPolicy(policy_id_2, number_of_periods, 0, [ursula1]).transact(
        {'from': alice1, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    #
    # Revoke policy
    #
    log.info("Revoking policy = " + str(policy_functions.revokePolicy(policy_id_1).estimateGas({'from': alice1})))
    tx = policy_functions.revokePolicy(policy_id_1).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    tx = policy_functions.revokePolicy(policy_id_2).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    #
    # Create policy with more periods
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 100
    log.info("First creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
             str(policy_functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula2]).estimateGas(
                 {'from': alice1, 'value': 10050})))
    tx = policy_functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula2]).transact(
        {'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    log.info("Second creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
             str(policy_functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula2]).estimateGas(
                 {'from': alice1, 'value': 10050})))
    tx = policy_functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula2]).transact(
        {'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)
    log.info("Third creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
             str(policy_functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1]).estimateGas(
                 {'from': alice1, 'value': 10050})))
    tx = policy_functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1]).transact(
        {'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)

    #
    # Mine and revoke policy
    #
    testerchain.time_travel(periods=10)
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=1)
    log.info("First mining after downtime = " + str(staker_functions.mint().estimateGas({'from': ursula1})))
    tx = staker_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining after downtime = " + str(staker_functions.mint().estimateGas({'from': ursula2})))
    tx = staker_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=10)
    log.info("First revoking policy after downtime = " +
             str(policy_functions.revokePolicy(policy_id_1).estimateGas({'from': alice1})))
    tx = policy_functions.revokePolicy(policy_id_1).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    log.info("Second revoking policy after downtime = " +
             str(policy_functions.revokePolicy(policy_id_2).estimateGas({'from': alice1})))
    tx = policy_functions.revokePolicy(policy_id_2).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    log.info("Second revoking policy after downtime = " +
             str(policy_functions.revokePolicy(policy_id_3).estimateGas({'from': alice1})))
    tx = policy_functions.revokePolicy(policy_id_3).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    #
    # Create policy with multiple nodes
    #
    policy_id_1 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(Policy.POLICY_ID_LENGTH))
    number_of_periods = 100
    log.info("First creating policy (3 nodes, 100 periods, first reward) = " +
             str(policy_functions
                 .createPolicy(policy_id_1, number_of_periods, 50, [ursula1, ursula2, ursula3])
                 .estimateGas({'from': alice1, 'value': 30150})))
    tx = policy_functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula1, ursula2, ursula3]).transact(
        {'from': alice1, 'value': 30150})
    testerchain.wait_for_receipt(tx)
    log.info("Second creating policy (3 nodes, 100 periods, first reward) = " +
             str(policy_functions
                 .createPolicy(policy_id_2, number_of_periods, 50, [ursula1, ursula2, ursula3])
                 .estimateGas({'from': alice1, 'value': 30150})))
    tx = policy_functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula1, ursula2, ursula3]).transact(
        {'from': alice1, 'value': 30150})
    testerchain.wait_for_receipt(tx)
    log.info("Third creating policy (2 nodes, 100 periods, first reward) = " +
             str(policy_functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1, ursula2]).estimateGas(
                 {'from': alice1, 'value': 20100})))
    tx = policy_functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1, ursula2]).transact(
        {'from': alice1, 'value': 20100})
    testerchain.wait_for_receipt(tx)

    for index in range(5):
        tx = staker_functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        tx = staker_functions.confirmActivity().transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
        tx = staker_functions.confirmActivity().transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(periods=1)

    tx = staker_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Check regular deposit
    #
    log.info("First deposit tokens = " + str(
        staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens = " + str(
        staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens = " + str(
        staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = staker_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # ApproveAndCall
    #
    testerchain.time_travel(periods=1)

    tx = staker_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First approveAndCall = " +
             str(token_functions.approveAndCall(staking_agent.contract_address,
                                                MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula1})))
    tx = token_functions.approveAndCall(staking_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second approveAndCall = " +
             str(token_functions.approveAndCall(staking_agent.contract_address, MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula2})))
    tx = token_functions.approveAndCall(staking_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third approveAndCall = " +
             str(token_functions.approveAndCall(staking_agent.contract_address,
                                                MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula3})))
    tx = token_functions.approveAndCall(staking_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Locking tokens
    #
    testerchain.time_travel(periods=1)

    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = staker_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First locking tokens = " +
             str(staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second locking tokens = " +
             str(staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third locking tokens = " +
             str(staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Divide stake
    #
    log.info("First divide stake = " + str(
        staker_functions.divideStake(1, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = staker_functions.divideStake(1, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second divide stake = " + str(
        staker_functions.divideStake(3, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = staker_functions.divideStake(3, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    #
    # Divide almost finished stake
    #
    testerchain.time_travel(periods=1)
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    log.info("Divide stake (next period is not confirmed) = " + str(
        staker_functions.divideStake(0, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Divide stake (next period is confirmed) = " + str(
        staker_functions.divideStake(0, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))

    #
    # Slashing tests
    #
    tx = staker_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    # Deploy adjudicator to estimate slashing method in StakingEscrow contract
    adjudicator, _ = testerchain.deploy_contract(
        'Adjudicator', staking_agent.contract.address, ALGORITHM_SHA256, MIN_ALLOWED_LOCKED - 1, 0, 2, 2
    )
    tx = staker_functions.setAdjudicator(adjudicator.address).transact()
    testerchain.wait_for_receipt(tx)
    adjudicator_functions = adjudicator.functions

    #
    # Slashing
    #
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Slash just value = " + str(
        adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    deposit = staker_functions.stakerInfo(ursula1).call()[0]
    unlocked = deposit - staker_functions.getLockedTokens(ursula1).call()
    tx = staker_functions.withdraw(unlocked).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("First slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Second slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Third slashing one sub stake and saving old one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Slashing two sub stakes and saving old one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    for index in range(18):
        tx = staker_functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(periods=1)

    tx = staker_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    deposit = staker_functions.stakerInfo(ursula1).call()[0]
    unlocked = deposit - staker_functions.getLockedTokens(ursula1, 1).call()
    tx = staker_functions.withdraw(unlocked).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Slashing two sub stakes, shortest and new one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sub_stakes_length = str(staker_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1)
    log.info("Slashing three sub stakes, two shortest and new one (" + sub_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    slashing_args = generate_args_for_slashing(testerchain, ursula_with_stamp, ursula1, corrupt_cfrag=False)
    log.info("Evaluating correct CFrag = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    print("********* All Done! *********")


if __name__ == "__main__":
    print("Starting Up...")
    analyzer = AnalyzeGas()
    estimate_gas(analyzer=analyzer)
    analyzer.to_json_file()
