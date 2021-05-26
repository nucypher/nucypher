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

from collections import defaultdict

import lmdb
import pytest
from eth_utils.crypto import keccak

from nucypher.control.emitters import WebEmitter
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nodes import Learner
from nucypher.network.trackers import AvailabilityTracker
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_IP_ADDRESS
from tests.mock.datastore import mock_lmdb_open

# Crash on server error by default
WebEmitter._crash_on_error_default = True

# Dont re-lock account in background while making commitments
LOCK_FUNCTION = TransactingPower.lock_account
TransactingPower.lock_account = lambda *a, **k: True

# Prevent halting the reactor via health checks during tests
AvailabilityTracker._halt_reactor = lambda *a, **kw: True

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


#
# Pytest configuration
#

pytest_plugins = [
    'tests.fixtures',  # Includes external fixtures module
]


def pytest_addoption(parser):
    parser.addoption("--run-nightly",
                     action="store_true",
                     default=False,
                     help="run tests even if they are marked as nightly")

    # class SetLearnerDebugMode((argparse.Action)):
    #     def __call__(self, *args, **kwargs):
    #         from nucypher.network.nodes import Learner
    #         Learner._DEBUG_MODE = True

    # parser.addoption("--track-character-lifecycles",
    #                  action=SetLearnerDebugMode,
    #                  default=False,
    #                  help="Track characters in a global... mutable... where everybody...")


def pytest_configure(config):
    message = "{0}: mark test as {0} to run (skipped by default, use '{1}' to include these tests)"
    config.addinivalue_line("markers", message.format("nightly", "--run-nightly"))


def pytest_collection_modifyitems(config, items):

    #
    # Handle slow tests marker
    #

    option_markers = {
        "--run-nightly": "nightly"
    }

    for option, marker in option_markers.items():
        option_is_set = config.getoption(option)
        if option_is_set:
            continue

        skip_reason = pytest.mark.skip(reason=f"need {option} option to run tests marked with '@pytest.mark.{marker}'")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip_reason)

    #
    # Handle Log Level
    #

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
        gmwe = global_mutable_where_everybody
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
def mock_datastore(monkeysession):
    monkeysession.setattr(lmdb, 'open', mock_lmdb_open)
    yield


@pytest.fixture(scope='session', autouse=True)
def mock_get_external_ip_from_url_source(session_mocker):
    target = 'nucypher.cli.actions.configure.determine_external_ip_address'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)


@pytest.fixture(scope='session', autouse=True)
def disable_check_grant_requirements(session_mocker):
    target = 'nucypher.characters.lawful.Alice._check_grant_requirements'
    session_mocker.patch(target, return_value=MOCK_IP_ADDRESS)
