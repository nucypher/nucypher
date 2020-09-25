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

import pytest

from nucypher.network.nodes import Learner


@pytest.mark.skip
def test_print_ursulas_bytes(blockchain_ursulas):
    """
    Helper test that can be manually executed to get version-specific ursulas' metadata,
    which can be later used in tests/integration/learning/test_learning_versions.py
    """

    print(f"\nursulas_v{Learner.LEARNER_VERSION} = (")
    for ursula in blockchain_ursulas:
        print(f"    '{bytes(ursula).hex()}',")
    print(")")
