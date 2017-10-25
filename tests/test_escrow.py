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
    escrow, txhash = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address, human_jury],
            deploy_transaction={'from': creator})
    assert txhash is not None

    # Give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(ursula, escrow.address) == 10000

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # But Jury can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': human_jury}).setLock(ursula, 500)
        chain.wait.for_receipt(tx)

    # Ursula transfers some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1000
    assert token.call().balanceOf(ursula) == 9000

    # Ursula asks for refund
    tx = escrow.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Jury cannot withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': human_jury}).withdraw(500)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # But Jury can lock
    tx = escrow.transact({'from': human_jury}).setLock(ursula, 500)
    chain.wait.for_receipt(tx)

    # And Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Now Jury unlocks some
    tx = escrow.transact({'from': human_jury}).setLock(ursula, 200)
    chain.wait.for_receipt(tx)

    # And Ursula can withdraw
    tx = escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 400
    assert token.call().balanceOf(ursula) == 9600

    # But can't withdraw all
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(400)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 400
    assert token.call().balanceOf(ursula) == 9600

    # Ursula can withdraw all after Jury unlocks all
    tx = escrow.transact({'from': human_jury}).setLock(ursula, 0)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula}).withdrawAll()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 0
    assert token.call().balanceOf(ursula) == 10000

    # Ursula transfers some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)

    # And Jury lock some
    tx = escrow.transact({'from': human_jury}).setLock(ursula, 500)
    chain.wait.for_receipt(tx)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # Destroy contract from creator and refund all to Ursula
    tx = escrow.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 0
    assert token.call().balanceOf(ursula) == 10000
