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

import random
import time
from collections import Counter

import pytest
from eth_utils import ValidationError
from pathlib import Path

from nucypher.blockchain.eth.agents import ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.sol.compile import ALLOWED_PATHS
from nucypher.crypto.powers import TransactingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.blockchain import TesterBlockchain


llamas = [
    (1, 0.1),

    (2, None),
    (2, None),
    (2, None),
    (2, None),
    (2, None),

    (2, 0.01),
    (2, 0.01),
    (2, 0.01),
    (2, 0.01),
    (2, 0.01),

    (2, 0.2),
    (2, 0.2),
    (2, 0.2),
    (2, 0.2),
    (2, 0.2),

    (2, 0.3),
    (2, 0.3),
    (2, 0.3),
    (2, 0.3),
    (2, 0.3),

]


@pytest.mark.parametrize('tx_count, delay', llamas)
def test_rapid_deployment_nonce_uniqueness(mocker, tx_count, delay):

    # Prepare compiler
    base_dir = Path(__file__).parent / 'contracts' / 'multiversion'
    v1_dir, v2_dir = base_dir / 'v1', base_dir / 'v2'

    # I am a contract administrator and I an compiling a new updated version of an existing contract...
    # Represents "Manually hardcoding" a new permitted compile path in compile.py
    # and new source directory on BlockchainDeployerInterface.SOURCES.
    ALLOWED_PATHS.append(base_dir)
    BlockchainDeployerInterface.SOURCES = (v1_dir, v2_dir)

    # Prepare chain
    BlockchainInterfaceFactory._interfaces.clear()
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm')
    blockchain_interface.connect()
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)  # Lets this test run in isolation

    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    nonce_spy = mocker.spy(BlockchainDeployerInterface, 'sign_and_broadcast_transaction')
    # get_code_size == 0? (post-deploy)

    contract_name = "VersionTest"
    registry = InMemoryContractRegistry()
    for i in range(tx_count):
        try:
            blockchain_interface.deploy_contract(deployer_address=origin,
                                                 registry=registry,
                                                 contract_name=contract_name,
                                                 contract_version="latest")
            if delay is not None:
                #FIXME (mutex?)
                time.sleep(delay)
        except ValidationError:
            raise
            nonces = Counter()
            for call_args in nonce_spy.call_args_list:
                transaction_dict = call_args.kwargs['transaction_dict']
                nonce = transaction_dict['nonce']
                nonces[nonce] += 1
            assert len(BlockchainInterfaceFactory._interfaces) == 1
            assert all(bool(count == 1) for nonce, count in nonces.items()), 'A nonce was reused.'


@pytest.mark.parametrize('tx_count, delay', llamas)
def test_nonce_stability_with_state_stress(mocker, tx_count, delay):

    base_dir = Path(__file__).parent / 'contracts' / 'stress'
    ALLOWED_PATHS.append(base_dir)
    stress_contract_dir = base_dir / 'array_push'
    BlockchainDeployerInterface.SOURCES = (str(stress_contract_dir), )

    # Prepare chain
    BlockchainInterfaceFactory._interfaces.clear()
    blockchain_interface = BlockchainDeployerInterface(provider_uri='tester://pyevm')
    blockchain_interface.connect()
    BlockchainInterfaceFactory.register_interface(interface=blockchain_interface)  # Lets this test run in isolation

    origin = blockchain_interface.client.accounts[0]
    blockchain_interface.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD, account=origin)
    blockchain_interface.transacting_power.activate()

    nonce_spy = mocker.spy(BlockchainDeployerInterface, 'sign_and_broadcast_transaction')
    # get_code_size == 0? (post-deploy)

    contract_name = "StressTest"
    registry = InMemoryContractRegistry()
    contract, receipt = blockchain_interface.deploy_contract(deployer_address=origin,
                                                             registry=registry,
                                                             contract_name=contract_name)
    for i in range(tx_count):
        try:
            txhash = contract.functions.append(2).transact()
        except ValidationError:
            nonces = Counter()
            for call_args in nonce_spy.call_args_list:
                transaction_dict = call_args.kwargs['transaction_dict']
                nonce = transaction_dict['nonce']
                nonces[nonce] += 1
            assert len(BlockchainInterfaceFactory._interfaces) == 1
            assert all(bool(count == 1) for nonce, count in nonces.items()), 'A nonce was reused.'


def test_nonce_stability_with_raw_transactions():
    BlockchainInterfaceFactory._interfaces.clear()
    testerchain, registry = TesterBlockchain.bootstrap_network()
    counter = Counter()
    for i in range(100):
        target = random.choice(testerchain.unassigned_accounts)
        nonce = testerchain.client.w3.eth.getTransactionCount(testerchain.etherbase_account, 'pending')
        counter[nonce] += 1
        tx = {
            'value': 100,
            'gas': 6_000_000,
            'gasPrice': 1,
            'chainId': testerchain.client.chain_id,
            'data': '00000000000000000000000000000'*10000,
            # Stress.
            # Create TX to append on-chain storage (append on array)
            # Use input to regulate stress level. (check for old state)
            # WARNING: be aware of exec. time itself biasing results
            # Later: Instrumentation for on-chan state and data inclusion at block hash
            # WCS: TX Uncled, commit to next period with out-of-order nonce or non-inclusion.
            # If the above is ruled out: The bug is within application code.
            # Current Severity: Identified an new unknown problem when broadcasting deployment Txs (nonce resuse)
            # Question: What characteristics cause reused nonce?
            'nonce': nonce,
            'from': testerchain.etherbase_account,
            'to': target
        }

        try:
            testerchain.sign_and_broadcast_transaction(transaction_dict=tx)
        except ValidationError:
            assert len(BlockchainInterfaceFactory._interfaces) == 1
            assert all(bool(count == 1) for nonce, count in counter.items()), 'A nonce was reused.'
            raise


def test_nonce_stability_with_token_agent():
    BlockchainInterfaceFactory._interfaces.clear()
    testerchain, registry = TesterBlockchain.bootstrap_network()
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
    counter = Counter()
    for i in range(100):
        target = random.choice(testerchain.unassigned_accounts)
        contract_function = token_agent.contract.functions.transfer(target, 100)
        try:
            testerchain.send_transaction(contract_function=contract_function,
                                         sender_address=testerchain.etherbase_account)
        except ValidationError:
            assert len(BlockchainInterfaceFactory._interfaces) == 1
            assert all(bool(count == 1) for nonce, count in counter.items()), 'A nonce was reused.'
            raise
