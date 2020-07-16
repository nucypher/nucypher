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
import pytest_twisted as pt

from tests.acceptance.cli.lifecycle import run_entire_cli_lifecycle


@pt.inlineCallbacks
def test_federated_cli_lifecycle(click_runner,
                                 testerchain,
                                 random_policy_label,
                                 federated_ursulas,
                                 custom_filepath,
                                 custom_filepath_2):
    yield run_entire_cli_lifecycle(click_runner,
                                   testerchain,
                                   random_policy_label,
                                   federated_ursulas,
                                   custom_filepath,
                                   custom_filepath_2)

    # for port in _ports_to_remove:
    #     del MOCK_KNOWN_URSULAS_CACHE[port]
    # MOCK_KNOWN_URSULAS_CACHE
