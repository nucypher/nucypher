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

from nucypher.characters.lawful import Ursula


def test_serialize_ursula(federated_ursulas):
    ursula = federated_ursulas.pop()
    ursula_as_bytes = bytes(ursula)
    ursula_object = Ursula.from_bytes(ursula_as_bytes)
    assert ursula == ursula_object
    ursula.stop()
