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
from eth_tester.exceptions import TransactionFailed


@pytest.mark.slow()
def test_create_token(testerchain):
    """
    These are tests for standard tokens taken from Consensys github:
    https://github.com/ConsenSys/Tokens/
    but some of the tests are converted from javascript to python
    """

    creator = testerchain.interface.w3.eth.accounts[0]
    account1 = testerchain.interface.w3.eth.accounts[1]
    account2 = testerchain.interface.w3.eth.accounts[2]

    # Create an ERC20 token
    token, txhash = testerchain.interface.deploy_contract('NuCypherToken', 10 ** 9)
    assert txhash is not None

    # Account balances
    assert 10 ** 9 == token.functions.balanceOf(creator).call()
    assert 0 == token.functions.balanceOf(account1).call()

    # Basic properties
    assert 'NuCypher' == token.functions.name().call()
    assert 18 == token.functions.decimals().call()
    assert 'NU' == token.functions.symbol().call()

    # Cannot send ETH to the contract because there is no payable function
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.interface.w3.eth.sendTransaction(
            {'from': testerchain.interface.w3.eth.coinbase, 'to': token.address, 'value': 10 ** 9})
        testerchain.wait_for_receipt(tx)

    # Can transfer tokens
    tx = token.functions.transfer(account1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(account1).call()
    assert 10 ** 9 - 10000 == token.functions.balanceOf(creator).call()
    tx = token.functions.transfer(account2, 10).transact({'from': account1})
    testerchain.wait_for_receipt(tx)
    assert 10000 - 10 == token.functions.balanceOf(account1).call()
    assert 10 == token.functions.balanceOf(account2).call()
    tx = token.functions.transfer(token.address, 10).transact({'from': account1})
    testerchain.wait_for_receipt(tx)
    assert 10 == token.functions.balanceOf(token.address).call()

    # Can burn own tokens
    tx = token.functions.burn(1).transact({'from': account2})
    testerchain.wait_for_receipt(tx)
    assert 9 == token.functions.balanceOf(account2).call()
    assert 10 ** 9 - 1 == token.functions.totalSupply().call()


@pytest.mark.slow()
def test_approve_and_call(testerchain):
    creator = testerchain.interface.w3.eth.accounts[0]
    account1 = testerchain.interface.w3.eth.accounts[1]
    account2 = testerchain.interface.w3.eth.accounts[2]

    token, _ = testerchain.interface.deploy_contract('NuCypherToken', 10 ** 9)
    mock, _ = testerchain.interface.deploy_contract('ReceiveApprovalMethodMock')

    # Approve some value and check allowance
    tx = token.functions.approve(account1, 100).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 100 == token.functions.allowance(creator, account1).call()
    assert 0 == token.functions.allowance(creator, account2).call()
    assert 0 == token.functions.allowance(account1, creator).call()
    assert 0 == token.functions.allowance(account1, account2).call()
    assert 0 == token.functions.allowance(account2, account1).call()

    # Use transferFrom with allowable value
    tx = token.functions.transferFrom(creator, account2, 50).transact({'from': account1})
    testerchain.wait_for_receipt(tx)
    assert 50 == token.functions.balanceOf(account2).call()
    assert 50 == token.functions.allowance(creator, account1).call()

    # The result of approveAndCall is increased allowance and method execution in the mock contract
    tx = token.functions.approveAndCall(mock.address, 25, testerchain.interface.w3.toBytes(111))\
        .transact({'from': account1})
    testerchain.wait_for_receipt(tx)
    assert 50 == token.functions.balanceOf(account2).call()
    assert 50 == token.functions.allowance(creator, account1).call()
    assert 25 == token.functions.allowance(account1, mock.address).call()
    assert account1 == mock.functions.sender().call()
    assert 25 == mock.functions.value().call()
    assert token.address == mock.functions.tokenContract().call()
    assert 111 == testerchain.interface.w3.toInt(mock.functions.extraData().call())
