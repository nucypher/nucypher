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
import random
from collections import Counter
from os.path import abspath, dirname

import pytest
import time
from eth_utils import ValidationError
from pathlib import Path

from nucypher.blockchain.eth.agents import ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler, SourceDirs
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.blockchain import TesterBlockchain

"""
TODO
----
Create TX to append on-chain storage (append on array)
Use input to regulate stress level. (check for old state)
WARNING: be aware of exec. time itself biasing results
Later: Instrumentation for on-chan state and data inclusion at block hash
WCS: TX Uncled, commit to next period with out-of-order nonce or non-inclusion.
If the above is ruled out: The bug is within application code.
Current Severity: Identified an new unknown problem when broadcasting deployment Txs (nonce resuse)
Question: What characteristics cause reused nonce?
"""


@pytest.fixture(scope='module')
def blockchain_interface():

    # Prepare compiler
    base_dir = os.path.join(dirname(abspath(__file__)), "contracts", "multiversion")
    v1_dir = os.path.join(base_dir, "v1")
    v2_dir = os.path.join(base_dir, "v2")
    root_dir = SolidityCompiler.default_contract_dir()
    solidity_compiler = SolidityCompiler(source_dirs=[SourceDirs(root_dir, {v2_dir}),
                                                      SourceDirs(root_dir, {v1_dir})])

    # Prepare chain
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm/2', compiler=solidity_compiler)
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)
    blockchain_interface.connect()
    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    return blockchain_interface


TX_FREQUENCY = [

    (1, 0.1),  # control

    (2, None),
    (3, None),
    (4, None),

    (2, 0.01),
    (3, 0.01),
    (4, 0.01),

    (2, 0.2),
    (3, 0.2),
    (4, 0.2),

    (2, 0.3),
    (3, 0.3),
    (4, 0.3),

]


@pytest.mark.parametrize('tx_count, delay', TX_FREQUENCY)
def test_rapid_deployment_nonce_uniqueness(mocker, tx_count, delay, blockchain_interface):

    contract_name = "VersionTest"
    registry = InMemoryContractRegistry()

    # Measure
    nonce_spy = mocker.spy(BlockchainDeployerInterface, 'sign_and_broadcast_transaction')
    for i in range(tx_count):
        try:
            blockchain_interface.deploy_contract(deployer_address=blockchain_interface.client.accounts[0],
                                                 registry=registry,
                                                 contract_name=contract_name,
                                                 contract_version="latest")


            # TODO: get_code_size == 0? (post-deploy)

            if delay is not None:
                time.sleep(delay)
        except ValidationError as e:
            continue  # TODO: ensure nonce exception is occurring here

    # Collect results
    nonces = Counter()
    for call_args in nonce_spy.call_args_list:
        transaction_dict = call_args.kwargs['transaction_dict']
        nonce = transaction_dict['nonce']
        nonces[nonce] += 1
    assert len(BlockchainInterfaceFactory._interfaces) == 1
    assert all(bool(count == 1) for nonce, count in nonces.items()), f'A nonce was reused. {json.dumps(nonces, indent=4)}'


@pytest.mark.skip('To be implemented')
@pytest.mark.parametrize('tx_count, delay', TX_FREQUENCY)
def test_nonce_stability_with_state_stress(mocker, tx_count, delay, blockchain_interface):

    nonce_spy = mocker.spy(BlockchainDeployerInterface, 'sign_and_broadcast_transaction')

    #
    # Measure
    #
    # get_code_size == 0? (post-deploy)

    contract_name = "StressTest"
    registry = InMemoryContractRegistry()
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=blockchain_interface.client.accounts[0],
                                                             registry=registry,
                                                             contract_name=contract_name)
    for i in range(tx_count):
        try:
            txhash = contract.functions.append(2).transact()
        except ValidationError:
            continue  # Permit failure

    # Collect Results
    nonces = Counter()
    for call_args in nonce_spy.call_args_list:
        transaction_dict = call_args.kwargs['transaction_dict']
        nonce = transaction_dict['nonce']
        nonces[nonce] += 1
    assert len(BlockchainInterfaceFactory._interfaces) == 1
    assert all(bool(count == 1) for nonce, count in nonces.items()), 'A nonce was reused.'


def test_nonce_stability_with_token_agent():

    # Setup
    BlockchainInterfaceFactory._interfaces.clear()
    testerchain, registry = TesterBlockchain.bootstrap_network()
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
    counter = Counter()

    # Measure
    for i in range(100):
        target = random.choice(testerchain.unassigned_accounts)
        contract_function = token_agent.contract.functions.transfer(target, 100)
        try:
            testerchain.send_transaction(contract_function=contract_function,
                                         sender_address=testerchain.etherbase_account)
        except ValidationError:
            continue  # Permit failure

    # Capture results
    assert len(BlockchainInterfaceFactory._interfaces) == 1
    assert all(bool(count == 1) for nonce, count in counter.items()), 'A nonce was reused.'


def test_nonce_stability_with_raw_transactions():

    # Setup
    BlockchainInterfaceFactory._interfaces.clear()
    testerchain, registry = TesterBlockchain.bootstrap_network()
    counter = Counter()

    # Measure
    for i in range(100):
        target = random.choice(testerchain.unassigned_accounts)
        nonce = testerchain.client.w3.eth.getTransactionCount(testerchain.etherbase_account, 'pending')
        counter[nonce] += 1
        tx = {
            'value': 100,
            'gas': 6_000_000,
            'gasPrice': 1,
            'chainId': testerchain.client.chain_id,
            'data': '00000000000000000000000000000'*10000,  # Large sized empty data
            'nonce': nonce,
            'from': testerchain.etherbase_account,
            'to': target
        }

        try:
            testerchain.sign_and_broadcast_transaction(transaction_dict=tx)
        except ValidationError:
            continue  # Permit failure

    # Capture results
    assert len(BlockchainInterfaceFactory._interfaces) == 1
    assert all(bool(count == 1) for nonce, count in counter.items()), 'A nonce was reused.'
