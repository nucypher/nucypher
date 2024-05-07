import json

import pytest

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.trackers.dkg import ActiveRitualTracker
from nucypher.cli.commands import ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.base import CharacterConfiguration
from tests.constants import FAKE_PASSWORD_CONFIRMED, MOCK_IP_ADDRESS


@pytest.fixture
def v4_config_file(tempfile_path, ursula_test_config, accounts):
    config_dictionary = {
        "federated_only": None,
        "checksum_address": None,
        "keystore_path": None,
        "domain": str(ursula_test_config.domain),
        "learn_on_same_thread": False,
        "abort_on_learning_error": False,
        "start_learning_now": False,
        "save_metadata": False,
        "node_storage": {"storage_type": ":memory:"},
        "lonely": False,
        "eth_provider_uri": ursula_test_config.eth_endpoint,
        "poa": None,
        "light": False,
        "signer_uri": ursula_test_config.signer_uri,
        "gas_strategy": "fast",
        "max_gas_price": None,
        "operator_address": accounts.ursulas_accounts[0],
        "rest_host": MOCK_IP_ADDRESS,
        "rest_port": ursula_test_config.rest_port,
        "db_filepath": "/root/.local/share/nucypher/ursula.db",
        "availability_check": False,
        "payment_method": "SubscriptionManager",
        "payment_provider": ursula_test_config.polygon_endpoint,
        "payment_network": str(
            ursula_test_config.domain
        ),  # doesn't really matter what this is
        "version": 4,
    }
    json.dump(config_dictionary, open(tempfile_path, "w"))
    return tempfile_path


def test_ursula_run_specified_config_file(
    testerchain,
    click_runner,
    mocker,
    ursulas,
    monkeypatch,
    v4_config_file,
):
    # migration spy
    migration_spy = mocker.spy(ursula, "migrate")

    # Mock DKG
    mocker.patch.object(ActiveRitualTracker, "start", autospec=True)

    # Mock Teacher Resolution
    from nucypher.characters.lawful import Ursula

    teacher = ursulas[0]
    mocker.patch.object(Ursula, "from_teacher_uri", return_value=teacher)

    # don't try unlocking keystore
    mocker.patch("nucypher.cli.utils.unlock_nucypher_keystore", return_value=True)

    # Mock worker qualification
    worker = ursulas[1]

    def set_staking_provider_address(operator, *args, **kwargs):
        operator.checksum_address = worker.checksum_address
        return True

    monkeypatch.setattr(Operator, "block_until_ready", set_staking_provider_address)

    # mock creation of non-dev ursula
    mocker.patch(
        "nucypher.cli.commands.ursula.make_cli_character", return_value=ursulas[1]
    )

    # skip preflight since not in dev mode
    mocker.patch("nucypher.characters.lawful.validate_operator_ip", return_value=None)

    # manual teacher
    run_args = (
        "ursula",
        "run",
        "--dry-run",
        "--debug",
        "--config-file",
        str(v4_config_file.absolute()),
        "--teacher",
        teacher.rest_url(),
        "--no-ip-checkup",
    )

    assert migration_spy.call_count == 0

    result = click_runner.invoke(
        nucypher_cli, run_args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED
    )

    # check that migration was indeed called
    assert migration_spy.call_count == 1

    # check that migration worked - updated to latest version
    with open(v4_config_file.absolute(), "r") as file:
        contents = file.read()
    config = json.loads(contents)
    config_version = config["version"]
    assert config_version > 4, "migrated to newer version"
    assert config_version == CharacterConfiguration.VERSION

    assert result.exit_code == 0, result.output
