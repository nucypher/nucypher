from collections import defaultdict

import pytest
from eth_utils.crypto import keccak

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.networks import (
    EthChain,
    NetworksInventory,
    PolygonChain,
    TACoDomain,
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nodes import Learner
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import MOCK_IP_ADDRESS, TESTERCHAIN_CHAIN_ID

# Don't re-lock accounts in the background while making commitments
LOCK_FUNCTION = TransactingPower.lock_account
TransactingPower.lock_account = lambda *a, **k: True

# Global test character cache
global_mutable_where_everybody = defaultdict(list)

Learner._DEBUG_MODE = False


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


# global_mutable_where_everybody = defaultdict(list)  # TODO: cleanup

@pytest.fixture(scope='module', autouse=True)
def check_character_state_after_test(request):
    from nucypher.network.nodes import Learner
    yield
    if Learner._DEBUG_MODE:
        module_name = request.module.__name__

        test_learners = global_mutable_where_everybody.get(module_name, [])
        # Those match the module name exactly; maybe there are some that we got by frame.
        for maybe_frame, learners in global_mutable_where_everybody.items():
            if f"{module_name}.py" in maybe_frame:
                test_learners.extend(learners)

        crashed = [learner for learner in test_learners if learner._crashed]

        if any(crashed):
            failure_message = ""
            for learner in crashed:
                failure_message += learner._crashed.getBriefTraceback()
            pytest.fail(f"Some learners crashed:{failure_message}")

        still_running = [learner for learner in test_learners if learner._learning_task.running]

        if any(still_running):
            offending_tests = set()
            for learner in still_running:
                offending_tests.add(learner._FOR_TEST)
                try:  # TODO: Deal with stop vs disenchant.  Currently stop is only for Ursula.
                    learner.stop()
                    learner._finalize()
                except AttributeError:
                    learner.disenchant()
            pytest.fail(f"Learners remaining: {still_running}.  Offending tests: {offending_tests} ")

        still_tracking  = [learner for learner in test_learners if hasattr(learner, 'work_tracker') and learner.work_tracker._tracking_task.running]
        for tracker in still_tracking:
            tracker.work_tracker.stop()


@pytest.fixture(scope='session', autouse=True)
def mock_get_external_ip_from_url_source(session_mocker):
    target = 'nucypher.cli.actions.configure.determine_external_ip_address'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)


@pytest.fixture(scope='session', autouse=True)
def disable_check_grant_requirements(session_mocker):
    target = 'nucypher.characters.lawful.Alice._check_grant_requirements'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)


@pytest.fixture(scope="session", autouse=True)
def mock_condition_blockchains(session_mocker):
    """adds testerchain's chain ID to permitted conditional chains"""
    session_mocker.patch.dict(
        "nucypher.policy.conditions.evm._CONDITION_CHAINS",
        {TESTERCHAIN_CHAIN_ID: "eth-tester/pyevm"},
    )
    testing_network = TACoDomain(
        TEMPORARY_DOMAIN, EthChain.TESTERCHAIN, PolygonChain.TESTERCHAIN
    )

    session_mocker.patch.object(
        NetworksInventory, "from_domain_name", return_value=testing_network
    )


@pytest.fixture(scope="module", autouse=True)
def mock_multichain_configuration(module_mocker, testerchain):
    module_mocker.patch.object(
        Operator, "_make_condition_provider", return_value=testerchain.provider
    )
