import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token_contract, _ = chain.provider.get_or_deploy_contract(
        'NuCypherKMSToken', deploy_args=[10 ** 9, 2 * 10 ** 9],
        deploy_transaction={'from': creator})
    return token_contract


@pytest.fixture()
def wallet_manager(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the wallet manager
    wallet_manager_contract, _ = chain.provider.get_or_deploy_contract(
            'WalletManager', deploy_args=[token.address, 10 ** 9, 50, 2],
            deploy_transaction={'from': creator, 'gas': 4000000})
    return wallet_manager_contract


def test_escrow(web3, chain, token, wallet_manager):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)
    assert 10000 == token.call().balanceOf(ursula)
    assert 10000 == token.call().balanceOf(alice)

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
        tx = wallet_manager.transact({'from': ursula}).lock(500, 2)
        chain.wait.for_receipt(tx)

    # And can't set lock using wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).updateLock(1)
        chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some money to wallets
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 1500)
    chain.wait.for_receipt(tx)
    assert 1500 == token.call().balanceOf(ursula_wallet.address)
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)
    assert 500 == token.call().balanceOf(alice_wallet.address)

    # Ursula asks for refund
    tx = ursula_wallet.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert 1000 == token.call().balanceOf(ursula_wallet.address)
    assert 9000 == token.call().balanceOf(ursula)

    # Alice can't withdraw from Ursula's wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': alice}).withdraw(1)
        chain.wait.for_receipt(tx)

    # Check that nothing is locked
    assert 0 == ursula_wallet.call().getLockedTokens()
    assert 0 == alice_wallet.call().getLockedTokens()

    # Ursula can't lock too low value (less then rate)
    # TODO uncomment
    # with pytest.raises(TransactionFailed):
    #     tx = wallet_manager.transact({'from': ursula}).lock(1000, 10)
    #     chain.wait.for_receipt(tx)

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = wallet_manager.transact({'from': ursula}).lock(1000, 2)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).lock(500, 6)
    chain.wait.for_receipt(tx)

    # Checks locked tokens in next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == ursula_wallet.call().getLockedTokens()
    assert 500 == alice_wallet.call().getLockedTokens()
    assert 1500 == wallet_manager.call().getAllLockedTokens()

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert 1000 == token.call().balanceOf(ursula_wallet.address)
    assert 9000 == token.call().balanceOf(ursula)

    # Ursula can deposit more tokens
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 500)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': ursula}).lock(500, 0)
    chain.wait.for_receipt(tx)
    assert 1500 == token.call().balanceOf(ursula_wallet.address)
    assert 8500 == token.call().balanceOf(ursula)

    # Wait 50 blocks and checks locking
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1500 == ursula_wallet.call().getLockedTokens()
    assert 1000 == ursula_wallet.call().calculateLockedTokens(web3.eth.blockNumber // 50, 1500, 1)
    assert 1000 == ursula_wallet.call().calculateLockedTokens(1)
    assert 500 == ursula_wallet.call().calculateLockedTokens(2)

    # Confirm activity and wait 50 blocks
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    assert 1500 == ursula_wallet.call().getLockedTokens()
    assert 1000 == ursula_wallet.call().calculateLockedTokens(1)
    assert 500 == ursula_wallet.call().calculateLockedTokens(2)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == ursula_wallet.call().getLockedTokens()
    assert 500 == ursula_wallet.call().calculateLockedTokens(1)

    # And Ursula can withdraw some tokens
    tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert 1400 == token.call().balanceOf(ursula_wallet.address)
    assert 8600 == token.call().balanceOf(ursula)

    # But Ursula can't withdraw all without mining for locked value
    # TODO complete method
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).withdrawAll()
    #     chain.wait.for_receipt(tx)

    # Ursula can deposit more tokens
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 500)
    chain.wait.for_receipt(tx)
    assert 1900 == token.call().balanceOf(ursula_wallet.address)
    tx = wallet_manager.transact({'from': ursula}).lock(500, 0)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)

    # Locked tokens will be updated in next period
    assert 1000 == ursula_wallet.call().getLockedTokens()
    assert 1100 == ursula_wallet.call().calculateLockedTokens(1)
    assert 100 == ursula_wallet.call().calculateLockedTokens(3)
    assert 0 == ursula_wallet.call().calculateLockedTokens(4)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1100 == ursula_wallet.call().getLockedTokens()
    assert 0 == ursula_wallet.call().calculateLockedTokens(3)

    # Ursula can increase lock
    tx = wallet_manager.transact({'from': ursula}).lock(500, 2)
    chain.wait.for_receipt(tx)
    assert 1100 == ursula_wallet.call().getLockedTokens()
    assert 1100 == ursula_wallet.call().calculateLockedTokens(1)
    assert 1100 == ursula_wallet.call().calculateLockedTokens(2)
    assert 600 == ursula_wallet.call().calculateLockedTokens(3)
    assert 0 == ursula_wallet.call().calculateLockedTokens(5)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1100 == ursula_wallet.call().getLockedTokens()

    # Alice can't deposit too low value (less then rate)
    # TODO uncomment after completing logic
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).deposit(100, 100)
    #     chain.wait.for_receipt(tx)

    # Alice increases lock by deposit more tokens
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).lock(500, 0)
    chain.wait.for_receipt(tx)
    assert 500 == alice_wallet.call().getLockedTokens()
    assert 1000 == alice_wallet.call().calculateLockedTokens(1)
    assert 750 == alice_wallet.call().calculateLockedTokens(2)
    assert 0 == alice_wallet.call().calculateLockedTokens(5)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == alice_wallet.call().getLockedTokens()

    # And increases locked blocks
    tx = wallet_manager.transact({'from': alice}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert 1000 == alice_wallet.call().getLockedTokens()
    assert 750 == alice_wallet.call().calculateLockedTokens(1)
    assert 750 == alice_wallet.call().calculateLockedTokens(2)
    assert 250 == alice_wallet.call().calculateLockedTokens(4)
    assert 0 == alice_wallet.call().calculateLockedTokens(5)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # # Destroy contract from creator and refund all to Ursula and Alice
    tx = wallet_manager.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert 0 == token.call().balanceOf(ursula_wallet.address)
    assert 0 == token.call().balanceOf(alice_wallet.address)
    assert 10000 == token.call().balanceOf(ursula)
    assert 10000 == token.call().balanceOf(alice)


def test_locked_distribution(web3, chain, token, wallet_manager):
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]
    miners = web3.eth.accounts[1:]
    amount = token.call().balanceOf(creator) // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx = token.transact({'from': creator}).transfer(miner, amount)
        chain.wait.for_receipt(tx)
        amount = amount // 2

    # Lock
    for index, miner in enumerate(miners[::-1]):
        balance = token.call().balanceOf(miner)
        tx = wallet_manager.transact({'from': miner}).createWallet()
        chain.wait.for_receipt(tx)
        wallet = wallet_manager.call().wallets(miner)
        tx = token.transact({'from': miner}).transfer(wallet, balance)
        chain.wait.for_receipt(tx)
        tx = wallet_manager.transact({'from': miner}).lock(balance, len(miners) - index + 1)
        chain.wait.for_receipt(tx)

    # Check current period
    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, 1, 1)
    assert NULL_ADDR == address_stop.lower()
    assert 0 == shift

    # Wait next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    n_locked = wallet_manager.call().getAllLockedTokens()
    assert n_locked > 0

    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, n_locked // 3, 1)
    assert miners[0].lower() == address_stop.lower()
    assert n_locked // 3 == shift

    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, largest_locked, 1)
    assert miners[1].lower() == address_stop.lower()
    assert 0 == shift

    address_stop, shift = wallet_manager.call().findCumSum(
        miners[1], largest_locked // 2 + 1, 1)
    assert miners[2].lower() == address_stop.lower()
    assert 1 == shift

    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, 1, 12)
    assert NULL_ADDR == address_stop.lower()
    assert 0 == shift

    for index, _ in enumerate(miners[:-1]):
        address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, 1, index + 3)
        assert miners[index + 1].lower() == address_stop.lower()
        assert 1 == shift


def test_mining(web3, chain, token, wallet_manager):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Ursula and Alice create wallets
    contract_factory = chain.provider.get_contract_factory("Wallet")
    tx = wallet_manager.transact({'from': ursula}).createWallet()
    chain.wait.for_receipt(tx)
    ursula_wallet = contract_factory(address=wallet_manager.call().wallets(ursula))
    tx = wallet_manager.transact({'from': alice}).createWallet()
    chain.wait.for_receipt(tx)
    alice_wallet = contract_factory(address=wallet_manager.call().wallets(alice))

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some money to wallets
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 1000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(wallet_manager.address)
    chain.wait.for_receipt(tx)
    assert token.call().isMiner(wallet_manager.address)

    # Ursula can't mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = wallet_manager.transact({'from': ursula}).lock(1000, 2)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).lock(500, 4)
    chain.wait.for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == wallet_manager.call().getAllLockedTokens()

    # Ursula can't use method from Miner contract
    with pytest.raises(TypeError):
        tx = wallet_manager.transact({'from': ursula}).mint(ursula, 1000, 1000, 1000, 1000)
        chain.wait.for_receipt(tx)

    # Only Ursula confirm next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1500 == wallet_manager.call().getAllLockedTokens()
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Checks that no error
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula and Alice mint tokens for last periods
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == wallet_manager.call().getAllLockedTokens()
    tx = wallet_manager.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 1033 == token.call().balanceOf(ursula_wallet.address)
    assert 517 == token.call().balanceOf(alice_wallet.address)

    # Only Ursula confirm activity for next period
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula can't confirm next period because end of locking
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 500 == wallet_manager.call().getAllLockedTokens()
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # But Alice can
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula mint tokens for next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 500 == wallet_manager.call().getAllLockedTokens()
    tx = wallet_manager.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    # But Alice can't mining because she did not confirmed activity
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': alice}).mint()
        chain.wait.for_receipt(tx)
    assert 1133 == token.call().balanceOf(ursula_wallet.address)
    assert 517 == token.call().balanceOf(alice_wallet.address)

    # Alice confirm 2 periods and mint tokens
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert 0 == wallet_manager.call().getAllLockedTokens()
    tx = wallet_manager.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 1133 == token.call().balanceOf(ursula_wallet.address)
    assert 617 == token.call().balanceOf(alice_wallet.address)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # Ursula can lock some tokens again
    tx = wallet_manager.transact({'from': ursula}).lock(500, 4)
    chain.wait.for_receipt(tx)
    assert 500 == ursula_wallet.call().getLockedTokens()
    assert 500 == ursula_wallet.call().calculateLockedTokens(2)
    assert 250 == ursula_wallet.call().calculateLockedTokens(5)
    assert 0 == ursula_wallet.call().calculateLockedTokens(6)
    # And can increase lock
    tx = wallet_manager.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)
    assert 600 == ursula_wallet.call().getLockedTokens()
    assert 600 == ursula_wallet.call().calculateLockedTokens(2)
    assert 350 == ursula_wallet.call().calculateLockedTokens(5)
    assert 100 == ursula_wallet.call().calculateLockedTokens(6)
    assert 0 == ursula_wallet.call().calculateLockedTokens(7)
    tx = wallet_manager.transact({'from': ursula}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert 600 == ursula_wallet.call().getLockedTokens()
    assert 600 == ursula_wallet.call().calculateLockedTokens(5)
    assert 350 == ursula_wallet.call().calculateLockedTokens(7)
    assert 100 == ursula_wallet.call().calculateLockedTokens(8)
    assert 0 == ursula_wallet.call().calculateLockedTokens(9)
    tx = wallet_manager.transact({'from': ursula}).lock(100, 1)
    chain.wait.for_receipt(tx)
    assert 700 == ursula_wallet.call().getLockedTokens()
    assert 700 == ursula_wallet.call().calculateLockedTokens(6)
    assert 450 == ursula_wallet.call().calculateLockedTokens(8)
    assert 200 == ursula_wallet.call().calculateLockedTokens(9)
    assert 0 == ursula_wallet.call().calculateLockedTokens(10)

    # Alice can withdraw all
    # TODO complete method
    # tx = wallet_manager.transact({'from': alice}).withdrawAll()
    # chain.wait.for_receipt(tx)
    tx = alice_wallet.transact({'from': alice}).withdraw(617)
    chain.wait.for_receipt(tx)
    assert 10117 == token.call().balanceOf(alice)

    # TODO test max confirmed periods
