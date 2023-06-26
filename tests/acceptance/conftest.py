import os
import random

import pytest
from web3 import Web3

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import CryptoPower, TransactingPower
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.logging import Logger
from tests.constants import (
    BONUS_TOKENS_FOR_TESTS,
    INSECURE_DEVELOPMENT_PASSWORD,
    MIN_STAKE_FOR_TESTS,
    MOCK_STAKING_CONTRACT_NAME,
    TEST_ETH_PROVIDER_URI,
)
from tests.utils.ape import deploy_contracts as ape_deploy_contracts
from tests.utils.ape import registry_from_ape_deployments
from tests.utils.blockchain import TesterBlockchain

test_logger = Logger("acceptance-test-logger")


@pytest.fixture(scope='session', autouse=True)
def nucypher_contracts(project):
    nucypher_contracts_dependency_api = project.dependencies["nucypher-contracts"]
    # simply use first entry - could be from github ('main') or local ('local')
    _, nucypher_contracts = list(nucypher_contracts_dependency_api.items())[0]
    nucypher_contracts.compile()
    return nucypher_contracts


@pytest.fixture(scope='module', autouse=True)
def deploy_contracts(nucypher_contracts, accounts):
    deployments = ape_deploy_contracts(
        nucypher_contracts=nucypher_contracts, accounts=accounts
    )
    return deployments


@pytest.fixture(scope='module', autouse=True)
def test_registry(nucypher_contracts, deploy_contracts):
    registry = registry_from_ape_deployments(nucypher_contracts, deployments=deploy_contracts)
    return registry


@pytest.fixture(scope='module')
def testerchain(project, test_registry) -> TesterBlockchain:
    # Extract the web3 provider containing EthereumTester from the ape project's chain manager
    provider = project.chain_manager.provider.web3.provider
    testerchain = TesterBlockchain(eth_provider=provider)
    BlockchainInterfaceFactory.register_interface(interface=testerchain, force=True)
    yield testerchain


@pytest.fixture(scope='module')
def threshold_staking(testerchain, test_registry):
    result = test_registry.search(contract_name=MOCK_STAKING_CONTRACT_NAME)[0]
    threshold_staking = testerchain.w3.eth.contract(
        address=result[2],
        abi=result[3]
    )
    return threshold_staking


@pytest.fixture(scope="module")
def staking_providers(testerchain, test_registry, threshold_staking):
    pre_application_agent = ContractAgency.get_agent(
        PREApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )
    blockchain = pre_application_agent.blockchain

    staking_providers = list()
    for provider_address, operator_address in zip(blockchain.stake_providers_accounts, blockchain.ursulas_accounts):
        provider_power = TransactingPower(account=provider_address, signer=Web3Signer(testerchain.client))
        provider_power.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

        # for a random amount
        amount = MIN_STAKE_FOR_TESTS + random.randrange(BONUS_TOKENS_FOR_TESTS)

        # initialize threshold stake
        tx = threshold_staking.functions.setRoles(provider_address).transact()
        testerchain.wait_for_receipt(tx)
        tx = threshold_staking.functions.setStakes(provider_address, amount, 0, 0).transact()
        testerchain.wait_for_receipt(tx)

        # We assume that the staking provider knows in advance the account of her operator
        pre_application_agent.bond_operator(staking_provider=provider_address,
                                            operator=operator_address,
                                            transacting_power=provider_power)

        operator_power = TransactingPower(
            account=operator_address, signer=Web3Signer(testerchain.client)
        )
        operator = Operator(
            is_me=True,
            operator_address=operator_address,
            domain=TEMPORARY_DOMAIN,
            registry=test_registry,
            transacting_power=operator_power,
            eth_provider_uri=testerchain.eth_provider_uri,
            signer=Web3Signer(testerchain.client),
            crypto_power=CryptoPower(power_ups=[operator_power]),
            payment_method=SubscriptionManagerPayment(
                eth_provider=testerchain.eth_provider_uri,
                network=TEMPORARY_DOMAIN,
                registry=test_registry,
            ),
        )
        operator.confirm_address()  # assume we always need a "pre-confirmed" operator for now.

        # track
        staking_providers.append(provider_address)

    yield staking_providers


@pytest.fixture(scope='module')
def manual_operator(testerchain):
    worker_private_key = os.urandom(32).hex()
    address = testerchain.provider.ethereum_tester.add_account(
        worker_private_key,
        password=INSECURE_DEVELOPMENT_PASSWORD
    )

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.to_wei('1', 'ether')}

    txhash = testerchain.client.w3.eth.send_transaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    yield address
