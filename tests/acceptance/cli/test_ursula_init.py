import json
import secrets
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from nucypher.blockchain.eth.agents import ContractAgency, TACoApplicationAgent
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_KEYSTORE_PASSWORD,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN,
)
from nucypher.crypto.powers import TransactingPower
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    TEST_POLYGON_PROVIDER_URI,
)
from tests.utils.ursula import select_test_port


@pytest.fixture(scope="module")
def mock_funded_account_password_keystore(
    tmp_path_factory,
    testerchain,
    threshold_staking,
    taco_application_agent,
    test_registry,
    deployer_account,
):
    """
    Generate a random keypair & password and create a local keystore. Then prepare a staking provider
    for ursula. Then check that the correct ursula ethereum key signs the commitment.
    """
    keystore = tmp_path_factory.mktemp("keystore", numbered=True)
    password = secrets.token_urlsafe(12)
    account = Account.create()
    path = keystore / f"{account.address}"
    json.dump(account.encrypt(password), open(path, "x+t"))

    testerchain.wait_for_receipt(
        testerchain.client.w3.eth.send_transaction(
            {
                "to": account.address,
                "from": testerchain.etherbase_account,
                "value": Web3.to_wei("100", "ether"),
            }
        )
    )

    # initialize threshold stake
    provider_address = testerchain.unassigned_accounts[0]
    threshold_staking.setRoles(provider_address, sender=deployer_account)
    threshold_staking.setStakes(
        provider_address,
        0,
        taco_application_agent.get_min_authorization(),
        sender=deployer_account,
    )

    provider_power = TransactingPower(
        account=provider_address, signer=Web3Signer(testerchain.client)
    )
    provider_power.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    taco_application_agent = ContractAgency.get_agent(
        TACoApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )
    taco_application_agent.bond_operator(
        staking_provider=provider_address,
        operator=account.address,
        transacting_power=provider_power,
    )

    return account, password, keystore


@pytest.mark.skip()
def test_ursula_and_local_keystore_signer_integration(
    click_runner,
    tmp_path,
    staking_providers,
    mocker,
    mock_funded_account_password_keystore,
    testerchain,
):
    config_root_path = tmp_path
    ursula_config_path = config_root_path / UrsulaConfiguration.generate_filename()
    worker_account, password, mock_keystore_path = mock_funded_account_password_keystore

    testerchain.wait_for_receipt(
        testerchain.client.w3.eth.send_transaction(
            {
                "to": worker_account,
                "from": testerchain.etherbase_account,
                "value": Web3.to_wei("100", "ether"),
            }
        )
    )

    #
    # Operator Steps
    #

    # Good signer...
    mock_signer_uri = f"keystore:{mock_keystore_path}"
    pre_config_signer = KeystoreSigner.from_signer_uri(
        uri=mock_signer_uri, testnet=True
    )
    assert worker_account.address in pre_config_signer.accounts

    deploy_port = select_test_port()

    init_args = (
        "ursula",
        "init",
        "--network",
        TEMPORARY_DOMAIN,
        "--operator-address",
        worker_account.address,
        "--config-root",
        str(config_root_path.absolute()),
        "--eth-endpoint",
        TEST_ETH_PROVIDER_URI,
        "--polygon-endpoint",
        TEST_POLYGON_PROVIDER_URI,
        "--rest-host",
        MOCK_IP_ADDRESS,
        "--rest-port",
        deploy_port,
        # The bit we are testing for here
        "--signer",
        mock_signer_uri,
    )

    cli_env = {
        NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: password,
        NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD: password,
    }
    result = click_runner.invoke(
        nucypher_cli, init_args, catch_exceptions=False, env=cli_env
    )
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the signer URI
    with open(ursula_config_path, "r") as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert (
            config_data["signer_uri"] == mock_signer_uri
        ), "Keystore URI was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(ursula_config_path)
    assert ursula_config.signer_uri == mock_signer_uri

    # Mock decryption of web3 client keystore
    mocker.patch.object(Account, "decrypt", return_value=worker_account.key)
    ursula_config.keystore.unlock(password=password)

    # Produce an Ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    ursula = ursula_config.produce()
    ursula.signer.unlock_account(account=worker_account.address, password=password)

    try:
        # Verify the keystore path is still preserved
        assert isinstance(ursula.signer, KeystoreSigner)
        assert isinstance(ursula.signer.path, Path), "Use Path"
        assert ursula.signer.path.absolute() == mock_keystore_path.absolute()

        # Show that we can produce the exact same signer as pre-config...
        assert pre_config_signer.path == ursula.signer.path

        # ...and that transactions are signed by the keystore signer
        txhash = ursula.confirm_address()
        receipt = testerchain.wait_for_receipt(txhash)
        transaction_data = testerchain.client.w3.eth.get_transaction(
            receipt["transactionHash"]
        )
        assert transaction_data["from"] == worker_account.address
    finally:
        ursula.stop()
