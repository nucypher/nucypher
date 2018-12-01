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
import pytest
from web3.contract import Contract


ALGORITHM_SHA256 = 1
secret = (123456).to_bytes(32, byteorder='big')


@pytest.fixture()
def escrow(testerchain):
    escrow, _ = testerchain.interface.deploy_contract('MinersEscrowForChallengeOverseerMock')
    return escrow


# @pytest.fixture(params=[False, True])
@pytest.fixture()
def challenge_contract(testerchain, escrow, request):
    # creator, client, bad_node, node1, node2, node3, *everyone_else = testerchain.interface.w3.eth.accounts

    contract, _ = testerchain.interface.deploy_contract('ChallengeOverseer', escrow.address, ALGORITHM_SHA256)

    # if request.param:
    #     secret_hash = testerchain.interface.w3.sha3(secret)
    #     dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract.address, secret_hash)
    #
    #     # Deploy second version of the government contract
    #     contract = testerchain.interface.w3.eth.contract(
    #         abi=contract.abi,
    #         address=dispatcher.address,
    #         ContractFactoryClass=Contract)

    return contract
