import pytest
from ethereum.tester import TransactionFailed


def test_escrow(web3, chain):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Create an ERC20 token
    token, txhash = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                10 ** 9, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={'from': creator})

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 10000
    assert token.call().balanceOf(alice) == 10000

    # Creator deploys the escrow
    escrow, txhash = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address, 1],
            deploy_transaction={'from': creator})
    assert txhash is not None

    # Ursula and Alice give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 2000)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(ursula, escrow.address) == 2000
    tx = token.transact({'from': alice}).approve(escrow.address, 500)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(alice, escrow.address) == 500

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1000
    assert token.call().balanceOf(ursula) == 9000
    tx = escrow.transact({'from': alice}).deposit(500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1500
    assert token.call().balanceOf(alice) == 9500

    # Ursula asks for refund
    tx = escrow.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(escrow.address) == 1000
    assert token.call().balanceOf(ursula) == 9500

    # Check that nothing is locked
    assert escrow.call().getLockedTokens(ursula) == 0
    assert escrow.call().getLockedTokens(alice) == 0
    assert escrow.call().getAllLockedTokens() == 0

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = escrow.transact({'from': ursula}).lock(500, 100)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 500
    assert escrow.call().getLockedTokens(alice) == 0
    assert escrow.call().getAllLockedTokens() == 500
    tx = escrow.transact({'from': alice}).lock(100, 200)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 500
    assert escrow.call().getLockedTokens(alice) == 100
    assert escrow.call().getAllLockedTokens() == 600

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1000
    assert token.call().balanceOf(ursula) == 9500

    # Wait 100 blocks
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert escrow.call().getLockedTokens(ursula) == 0
    assert escrow.call().getAllLockedTokens() == 100

    # And Ursula can withdraw some tokens
    tx = escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 900
    assert token.call().balanceOf(ursula) == 9600

    # And Ursula can withdraw all
    tx = escrow.transact({'from': ursula}).withdrawAll()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 500
    assert token.call().balanceOf(ursula) == 10000
    assert escrow.call().getLockedTokens(ursula) == 0
    assert escrow.call().getAllLockedTokens() == 100

    # Ursula transfers some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    # And lock some of them
    tx = escrow.transact({'from': ursula}).lock(500, 100)
    chain.wait.for_receipt(tx)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # Destroy contract from creator and refund all to Ursula and Alice
    tx = escrow.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 0
    assert token.call().balanceOf(ursula) == 10000
    assert token.call().balanceOf(alice) == 10000
