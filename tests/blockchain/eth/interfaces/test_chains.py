"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
def test_testerchain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert 'tester' in testerchain.interface.provider_uri

    # ... and that there are already some blocks mined
    assert testerchain.interface.w3.eth.blockNumber >= 0


