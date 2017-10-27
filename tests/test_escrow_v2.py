import pytest
from ethereum.tester import TransactionFailed


def test_escrow_v2(web3, chain):
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
    wallet_manager, txhash = chain.provider.get_or_deploy_contract(
            'WalletManager', deploy_args=[token.address, 1],
            deploy_transaction={'from': creator})
    assert txhash is not None

    # Ursula and Alice create wallets
    contract_factory = chain.provider.get_contract_factory("Wallet")
    tx = wallet_manager.transact({'from': ursula}).createWallet()
    chain.wait.for_receipt(tx)
    ursula_wallet = contract_factory(address=wallet_manager.call().wallets(ursula))
    tx = wallet_manager.transact({'from': alice}).createWallet()
    chain.wait.for_receipt(tx)
    alice_wallet = contract_factory(address=wallet_manager.call().wallets(alice))

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some money to wallets
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 1000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 1000
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(alice_wallet.address) == 500

    # Ursula asks for refund
    tx = ursula_wallet.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(ursula_wallet.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Alice can't withdraw from Ursula's wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': alice}).withdraw(1)
        chain.wait.for_receipt(tx)

    # And can't lock anything in Ursula's wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': alice}).lock(1, 100)
        chain.wait.for_receipt(tx)

    # Check that nothing is locked
    assert ursula_wallet.call().getLockedTokens() == 0
    assert alice_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getAllLockedTokens() == 0

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = ursula_wallet.transact({'from': ursula}).lock(500, 100)
    chain.wait.for_receipt(tx)
    assert ursula_wallet.call().getLockedTokens() == 500
    assert alice_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getLockedTokens(ursula) == 500
    assert wallet_manager.call().getAllLockedTokens() == 500
    tx = alice_wallet.transact({'from': alice}).lock(100, 200)
    chain.wait.for_receipt(tx)
    assert ursula_wallet.call().getLockedTokens() == 500
    assert alice_wallet.call().getLockedTokens() == 100
    assert wallet_manager.call().getLockedTokens(alice) == 100
    assert wallet_manager.call().getAllLockedTokens() == 600

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Wait 100 blocks
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert ursula_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getAllLockedTokens() == 100

    # And Ursula can withdraw some tokens
    tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 400
    assert token.call().balanceOf(ursula) == 9600

    # Ursula lock some of tokens again
    tx = ursula_wallet.transact({'from': ursula}).lock(200, 100)
    chain.wait.for_receipt(tx)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # Destroy contract from creator and refund all to Ursula and Alice
    tx = wallet_manager.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 0
    assert token.call().balanceOf(alice_wallet.address) == 0
    assert token.call().balanceOf(ursula) == 10000
    assert token.call().balanceOf(alice) == 10000
