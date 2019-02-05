#!/usr/bin/env python3


"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import coincurve
import json
import os

from cryptography.hazmat.primitives.asymmetric import ec
from eth_utils import to_canonical_address

from nucypher.policy.models import IndisputableEvidence
from umbral import pre
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer, Signature

import time
from os.path import abspath, dirname

import io
import re

from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from twisted.logger import globalLogPublisher, Logger, jsonFileLogObserver, ILogObserver
from zope.interface import provider

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import (
    MIN_ALLOWED_LOCKED,
    MIN_LOCKED_PERIODS,
    POLICY_ID_LENGTH
)
from nucypher.utilities.sandbox.blockchain import TesterBlockchain


ALGORITHM_SHA256 = 1


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


# TODO organize support functions
def generate_args_for_slashing(testerchain, miner, corrupt: bool = True):
    def sign_data(data, umbral_privkey):
        umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)

        # Prepare hash of the data
        hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
        hash_ctx.update(data)
        data_hash = hash_ctx.finalize()

        # Sign data and calculate recoverable signature
        cryptography_priv_key = umbral_privkey.to_cryptography_privkey()
        signature_der_bytes = cryptography_priv_key.sign(data, ec.ECDSA(hashes.SHA256()))
        signature = Signature.from_bytes(signature_der_bytes, der_encoded=True)
        recoverable_signature = bytes(signature) + bytes([0])
        pubkey_bytes = coincurve.PublicKey.from_signature_and_message(recoverable_signature, data_hash, hasher=None) \
            .format(compressed=False)
        if pubkey_bytes != umbral_pubkey_bytes:
            recoverable_signature = bytes(signature) + bytes([1])
        return recoverable_signature

    delegating_privkey = UmbralPrivateKey.gen_key()
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    signing_privkey = UmbralPrivateKey.gen_key()
    signer = Signer(signing_privkey)
    priv_key_bob = UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()
    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=pub_key_bob,
                                 threshold=2,
                                 N=4,
                                 sign_delegating_key=False,
                                 sign_receiving_key=False)
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_privkey.get_pubkey())
    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=os.urandom(34))
    capsule_bytes = capsule.to_bytes()
    if corrupt:
        cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    requester_umbral_private_key = UmbralPrivateKey.gen_key()
    requester_umbral_public_key_bytes = requester_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    miner_umbral_private_key = UmbralPrivateKey.gen_key()
    miner_umbral_public_key_bytes = miner_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)
    # Sign Umbral public key using eth-key
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(miner_umbral_public_key_bytes)
    miner_umbral_public_key_hash = hash_ctx.finalize()
    address = to_canonical_address(miner)
    sig_key = testerchain.interface.provider.ethereum_tester.backend._key_lookup[address]
    signed_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))

    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    return (capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)


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
    web3 = testerchain.interface.w3

    # Accounts
    origin, ursula1, ursula2, ursula3, alice1, *everyone_else = testerchain.interface.w3.eth.accounts

    # Contracts
    token_agent = NucypherTokenAgent(blockchain=testerchain)
    miner_agent = MinerAgent(blockchain=testerchain)
    policy_agent = PolicyAgent(blockchain=testerchain)

    # Contract Callers
    token_functions = token_agent.contract.functions
    miner_functions = miner_agent.contract.functions
    policy_functions = policy_agent.contract.functions

    analyzer.start_collection()
    print("********* Estimating Gas *********")

    #
    # Pre deposit tokens
    #
    tx = token_functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 5).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    log.info("Pre-deposit tokens for 5 owners = " + str(miner_functions.preDeposit(everyone_else[0:5],
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
        token_functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6).estimateGas({'from': ursula1})))
    tx = token_functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = token_functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Ursula and Alice transfer some tokens to the escrow and lock them
    #
    log.info("First initial deposit tokens = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second initial deposit tokens = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third initial deposit tokens = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and confirm activity
    #
    testerchain.time_travel(periods=1)
    log.info("First confirm activity = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First mining (1 stake) = " + str(miner_functions.mint().estimateGas({'from': ursula1})))
    tx = miner_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining (1 stake) = " + str(miner_functions.mint().estimateGas({'from': ursula2})))
    tx = miner_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining (1 stake) = " + str(miner_functions.mint().estimateGas({'from': ursula3})))
    tx = miner_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First confirm activity again = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity again = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity again = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Confirm again
    #
    testerchain.time_travel(periods=1)
    log.info("First confirm activity + mint = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity + mint = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity + mint = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Get locked tokens
    #
    log.info("Getting locked tokens = " + str(miner_functions.getLockedTokens(ursula1).estimateGas()))

    #
    # Wait 1 period and withdraw tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First withdraw = " + str(miner_functions.withdraw(1).estimateGas({'from': ursula1})))
    tx = miner_functions.withdraw(1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second withdraw = " + str(miner_functions.withdraw(1).estimateGas({'from': ursula2})))
    tx = miner_functions.withdraw(1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third withdraw = " + str(miner_functions.withdraw(1).estimateGas({'from': ursula3})))
    tx = miner_functions.withdraw(1).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and confirm activity
    #
    testerchain.time_travel(periods=1)
    log.info("First confirm activity after downtime = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity after downtime  = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity after downtime  = " +
             str(miner_functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Ursula and Alice deposit some tokens to the escrow again
    #
    log.info("First deposit tokens again = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens again = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens again = " +
             str(miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Wait 1 period and mint tokens
    #
    testerchain.time_travel(periods=1)
    log.info("First mining again = " + str(miner_functions.mint().estimateGas({'from': ursula1})))
    tx = miner_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining again = " + str(miner_functions.mint().estimateGas({'from': ursula2})))
    tx = miner_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining again = " + str(miner_functions.mint().estimateGas({'from': ursula3})))
    tx = miner_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Create policy
    #
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
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
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(POLICY_ID_LENGTH))
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
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=1)
    log.info("First mining after downtime = " + str(miner_functions.mint().estimateGas({'from': ursula1})))
    tx = miner_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining after downtime = " + str(miner_functions.mint().estimateGas({'from': ursula2})))
    tx = miner_functions.mint().transact({'from': ursula2})
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
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(POLICY_ID_LENGTH))
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
        tx = miner_functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        tx = miner_functions.confirmActivity().transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
        tx = miner_functions.confirmActivity().transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(periods=1)

    tx = miner_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Check regular deposit
    #
    log.info("First deposit tokens = " + str(
        miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens = " + str(
        miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens = " + str(
        miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # ApproveAndCall
    #
    testerchain.time_travel(periods=1)

    tx = miner_functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First approveAndCall = " +
             str(token_functions.approveAndCall(miner_agent.contract_address,
                                                MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula1})))
    tx = token_functions.approveAndCall(miner_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second approveAndCall = " +
             str(token_functions.approveAndCall(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula2})))
    tx = token_functions.approveAndCall(miner_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third approveAndCall = " +
             str(token_functions.approveAndCall(miner_agent.contract_address,
                                                MIN_ALLOWED_LOCKED * 2,
                                                web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula3})))
    tx = token_functions.approveAndCall(miner_agent.contract_address,
                                        MIN_ALLOWED_LOCKED * 2,
                                        web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Locking tokens
    #
    testerchain.time_travel(periods=1)

    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First locking tokens = " +
             str(miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second locking tokens = " +
             str(miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third locking tokens = " +
             str(miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    #
    # Divide stake
    #
    log.info("First divide stake = " + str(
        miner_functions.divideStake(1, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = miner_functions.divideStake(1, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second divide stake = " + str(
        miner_functions.divideStake(3, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = miner_functions.divideStake(3, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    #
    # Divide almost finished stake
    #
    testerchain.time_travel(periods=1)
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    log.info("Divide stake (next period is not confirmed) = " + str(
        miner_functions.divideStake(0, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Divide stake (next period is confirmed) = " + str(
        miner_functions.divideStake(0, MIN_ALLOWED_LOCKED, 2).estimateGas({'from': ursula1})))

    # Slashing tests
    tx = miner_functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    # Deploy adjudicator mock to estimate slashing method in MinersEscrow contract
    adjudicator, _ = testerchain.interface.deploy_contract(
        'MiningAdjudicator', miner_agent.contract.address, ALGORITHM_SHA256, MIN_ALLOWED_LOCKED - 1, 0, 2, 2
    )
    tx = miner_functions.setMiningAdjudicator(adjudicator.address).transact()
    testerchain.wait_for_receipt(tx)
    adjudicator_functions = adjudicator.functions

    # Slashing
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Slash just value = " + str(
        adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    deposit = miner_functions.minerInfo(ursula1).call()[0]
    unlocked = deposit - miner_functions.getLockedTokens(ursula1).call()
    tx = miner_functions.withdraw(unlocked).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("First slashing one sub stake and saving old one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Second slashing one sub stake and saving old one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Third slashing one sub stake and saving old one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Slashing two sub stakes and saving old one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    for index in range(18):
        tx = miner_functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(periods=1)

    tx = miner_functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    deposit = miner_functions.minerInfo(ursula1).call()[0]
    unlocked = deposit - miner_functions.getLockedTokens(ursula1, 1).call()
    tx = miner_functions.withdraw(unlocked).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Slashing two sub stakes, shortest and new one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    sug_stakes_length = str(miner_functions.getSubStakesLength(ursula1).call())
    slashing_args = generate_args_for_slashing(testerchain, ursula1)
    log.info("Slashing three sub stakes, two shortest and new one (" + sug_stakes_length + " sub stakes) = " +
             str(adjudicator_functions.evaluateCFrag(*slashing_args).estimateGas({'from': alice1})))
    tx = adjudicator_functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    slashing_args = generate_args_for_slashing(testerchain, ursula1, corrupt=False)
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
