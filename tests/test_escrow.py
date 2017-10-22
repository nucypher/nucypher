import pytest
from ethereum.tester import TransactionFailed


def test_escrow(web3, chain):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    human_jury = web3.eth.accounts[2]

    # Create an ERC20 token
    token, txhash = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                10 ** 9, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={'from': creator})

    # Give Ursula some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 10000

    # Ursula deploys the escrow
    ursula_escrow, txhash = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address, human_jury],
            deploy_transaction={'from': ursula})
    assert txhash is not None

    # Give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(ursula_escrow.address, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(ursula, ursula_escrow.address) == 10000

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = ursula_escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # But Jury can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = ursula_escrow.transact({'from': human_jury}).setLock(ursula, 500)
        chain.wait.for_receipt(tx)

    # Ursula transfers some tokens to the escrow
    tx = ursula_escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 1000
    assert token.call().balanceOf(ursula) == 9000

    # Ursula asks for refund
    tx = ursula_escrow.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(ursula_escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Jury cannot withdraw
    with pytest.raises(TransactionFailed):
        tx = ursula_escrow.transact({'from': human_jury}).withdraw(500)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # But Jury can lock
    tx = ursula_escrow.transact({'from': human_jury}).setLock(ursula, 500)
    chain.wait.for_receipt(tx)

    # And Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = ursula_escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Now Jury unlocks some
    tx = ursula_escrow.transact({'from': human_jury}).setLock(ursula, 200)
    chain.wait.for_receipt(tx)

    # And Ursula can withdraw
    tx = ursula_escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 400
    assert token.call().balanceOf(ursula) == 9600
