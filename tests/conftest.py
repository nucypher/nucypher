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

import pytest

from nucypher.characters.control.emitters import WebEmitter
from nucypher.crypto.powers import TransactingPower
from nucypher.network.trackers import AvailabilityTracker
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

# Crash on server error by default
WebEmitter._crash_on_error_default = True

# Dont re-lock account in background while making commitments
LOCK_FUNCTION = TransactingPower.lock_account
TransactingPower.lock_account = lambda *a, **k: True

# Disable any hardcoded preferred teachers during tests.
TEACHER_NODES = dict()

# Prevent halting the reactor via health checks during tests
AvailabilityTracker._halt_reactor = lambda *a, **kw: True

# Global test character cache
global_mutable_where_everybody = defaultdict(list)

##########################################


@pytest.fixture(autouse=True, scope='session')
def __very_pretty_and_insecure_scrypt_do_not_use():
    """
    # WARNING: DO NOT USE THIS CODE ANYWHERE #

    Mocks Scrypt derivation function for the duration of
    the test session in order to improve test performance.
    """

    # Capture Scrypt derivation method
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    original_derivation_function = Scrypt.derive

    # One-Time Insecure Password
    insecure_password = bytes(INSECURE_DEVELOPMENT_PASSWORD, encoding='utf8')

    # Patch Method
    def __insecure_derive(*args, **kwargs):
        """Temporarily replaces Scrypt.derive for mocking"""
        return insecure_password

    # Disable Scrypt KDF
    Scrypt.derive = __insecure_derive
    yield
    # Re-Enable Scrypt KDF
    Scrypt.derive = original_derivation_function

############################################


@pytest.fixture(scope='module')
def monkeymodule():
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
    parser.addoption("--runslow",
                     action="store_true",
                     default=False,
                     help="run tests even if they are marked as slow")
    parser.addoption("--run-nightly",
                     action="store_true",
                     default=False,
                     help="run tests even if they are marked as nightly")


def pytest_configure(config):
    message = "{0}: mark test as {0} to run (skipped by default, use '{1}' to include these tests)"
    config.addinivalue_line("markers", message.format("slow", "--runslow"))
    config.addinivalue_line("markers", message.format("nightly", "--run-nightly"))


def pytest_collection_modifyitems(config, items):

    #
    # Handle slow tests marker
    #

    option_markers = {
        "--runslow": "slow",
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


@pytest.fixture(scope='module', autouse=True)
def check_character_state_after_test(request):
    # TODO: Maybe patch here instead of the debug nonsense?  # TODO: Make sense of this TODO
    yield
    cleanup_gmwe(request)


def cleanup_gmwe(request, fail_with_active: bool = True):
    module_name = request.module.__name__
    module_characters = global_mutable_where_everybody.get(module_name, [])

    # Those match the module name exactly; maybe there are some that we got by frame.
    for maybe_frame, learners in global_mutable_where_everybody.items():
        if f"{module_name}.py" in maybe_frame:
            module_characters.extend(learners)

    faulty_characters = [char for char in module_characters if char._crashed]  # TODO: "crash" -> "fault"
    if any(faulty_characters):
        failure_message = ""
        for char in faulty_characters:
            failure_message += char._crashed.getBriefTraceback()
        pytest.fail(f"Characters services crashed:{failure_message}")

    active_characters = [char for char in module_characters if char.is_running()]
    if any(active_characters):
        for character in active_characters:
            try:  # TODO: Deal with stop vs disenchant.  Currently stop is only for Ursula.
                character.stop()
            except AttributeError:
                character.disenchant()
        if fail_with_active:
            pytest.fail(f"Characters services are actively running: {active_characters} ")
