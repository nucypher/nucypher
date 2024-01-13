from collections import defaultdict

import pytest
from eth_utils.crypto import keccak

from nucypher.blockchain.eth.actors import Operator
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import (
    MOCK_IP_ADDRESS,
    TESTERCHAIN_CHAIN_ID,
)

# Global test character cache
global_mutable_where_everybody = defaultdict(list)



@pytest.fixture(autouse=True, scope='session')
def __very_pretty_and_insecure_scrypt_do_not_use(request):
    """
    # WARNING: DO NOT USE THIS CODE ANYWHERE #

    Mocks Scrypt derivation function for the duration of
    the test session in order to improve test performance.
    """

    # Capture Scrypt derivation method
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    original_derivation_function = Scrypt.derive

    # Patch Method
    def __insecure_derive(_scrypt, key_material: bytes):
        """Temporarily replaces Scrypt.derive for mocking"""
        return keccak(key_material)

    # Disable Scrypt KDF
    Scrypt.derive = __insecure_derive
    yield
    # Re-Enable Scrypt KDF
    Scrypt.derive = original_derivation_function


@pytest.fixture(scope='session')
def monkeysession():
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="module")
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


#
# Pytest configuration
#


pytest_plugins = [
    'pytest-nucypher',  # Includes external fixtures module via plugin
]


def pytest_collection_modifyitems(config, items):
    log_level_name = config.getoption("--log-level", "info", skip=True)
    GlobalLoggerSettings.stop_sentry_logging()
    GlobalLoggerSettings.set_log_level(log_level_name)
    GlobalLoggerSettings.start_text_file_logging()
    GlobalLoggerSettings.start_json_file_logging()


@pytest.fixture(scope='session', autouse=True)
def mock_get_external_ip_from_url_source(session_mocker):
    target = 'nucypher.cli.actions.configure.determine_external_ip_address'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)


@pytest.fixture(scope='session', autouse=True)
def disable_check_grant_requirements(session_mocker):
    target = 'nucypher.characters.lawful.Alice._check_grant_requirements'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)


@pytest.fixture(scope="module", autouse=True)
def mock_condition_blockchains(module_mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    module_mocker.patch.dict(
        "nucypher.policy.conditions.evm._CONDITION_CHAINS",
        {TESTERCHAIN_CHAIN_ID: "eth-tester/pyevm"},
    )


@pytest.fixture(scope="module", autouse=True)
def mock_multichain_configuration(module_mocker, testerchain):
    module_mocker.patch.object(
        Operator, "_make_condition_provider", return_value=testerchain.provider
    )
