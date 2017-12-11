import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token_contract, _ = chain.provider.get_or_deploy_contract(
        'HumanStandardToken', deploy_args=[
            10 ** 9, 2 * 10 ** 9, 'NuCypher KMS', 6, 'KMS'],
        deploy_transaction={'from': creator})
    return token_contract


@pytest.fixture()
def wallet_manager(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the wallet manager
    wallet_manager_contract, _ = chain.provider.get_or_deploy_contract(
            'WalletManager', deploy_args=[token.address, 10 ** 9, 50],
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
    assert token.call().balanceOf(ursula) == 10000
    assert token.call().balanceOf(alice) == 10000

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
        tx = wallet_manager.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)

    # And can't set lock using wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).setLock(1, 100, 1)
        chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some money to wallets
    tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 1500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 1500
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(alice_wallet.address) == 500

    # Ursula asks for refund
    tx = ursula_wallet.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(ursula_wallet.address) == 1000
    assert token.call().balanceOf(ursula) == 9000

    # Alice can't withdraw from Ursula's wallet
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': alice}).withdraw(1)
        chain.wait.for_receipt(tx)

    # Check that nothing is locked
    assert ursula_wallet.call().getLockedTokens() == 0
    assert alice_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getAllLockedTokens() == 0

    # Ursula can't lock too low value (less then rate)
    # TODO uncomment
    # with pytest.raises(TransactionFailed):
    #     tx = wallet_manager.transact({'from': ursula}).lock(1000, 10)
    #     chain.wait.for_receipt(tx)

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = wallet_manager.transact({'from': ursula}).lock(1000, 100)
    chain.wait.for_receipt(tx)
    assert ursula_wallet.call().getLockedTokens() == 1000
    assert alice_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getLockedTokens(ursula) == 1000
    assert wallet_manager.call().getAllLockedTokens() == 1000
    tx = wallet_manager.transact({'from': alice}).lock(500, 200)
    chain.wait.for_receipt(tx)
    assert ursula_wallet.call().getLockedTokens() == 1000
    assert alice_wallet.call().getLockedTokens() == 500
    assert wallet_manager.call().getLockedTokens(alice) == 500
    assert wallet_manager.call().getAllLockedTokens() == 1500

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 1000
    assert token.call().balanceOf(ursula) == 9000

    # And Ursula can't penalize anyone
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).penalize(ursula, 100)
        chain.wait.for_receipt(tx)

    # Creator can't penalize Ursula by burning tokens which exceeded her locked value
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': creator}).penalize(ursula, 2000)
        chain.wait.for_receipt(tx)

    # But can penalize Ursula by burning some locked tokens
    tx = wallet_manager.transact({'from': creator}).penalize(ursula, 100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 900
    assert ursula_wallet.call().getLockedTokens() == 900
    assert wallet_manager.call().getAllLockedTokens() == 1400

    # Wait 100 blocks
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert ursula_wallet.call().getLockedTokens() == 0
    assert wallet_manager.call().getAllLockedTokens() == 500

    # And Ursula can withdraw some tokens
    tx = ursula_wallet.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 800
    assert token.call().balanceOf(ursula) == 9100

    # But Ursula can't lock some of tokens again without mining for locked value
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).lock(200, 100)
        chain.wait.for_receipt(tx)

    # Alice increases lock by transfer and lock more tokens
    tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).lock(500, 0)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(alice) == 1000
    assert wallet_manager.call().getLockedTokens(alice, web3.eth.blockNumber + 100) == 0
    # And increases locked blocks
    tx = wallet_manager.transact({'from': alice}).lock(0, 100)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(alice) == 1000
    assert wallet_manager.call().getLockedTokens(alice, web3.eth.blockNumber + 100) == 1000
    assert wallet_manager.call().getLockedTokens(alice, web3.eth.blockNumber + 200) == 0

    # # Ursula can't destroy contract
    # TODO fix bug
    # with pytest.raises(TransactionFailed):
    #     tx = wallet_manager.transact({'from': ursula}).destroy()
    #     chain.wait.for_receipt(tx)

    # # Destroy contract from creator and refund all to Ursula and Alice
    # TODO fix bug
    # tx = wallet_manager.transact({'from': creator}).destroy()
    # chain.wait.for_receipt(tx)
    # assert token.call().balanceOf(ursula_wallet.address) == 0
    # assert token.call().balanceOf(alice_wallet.address) == 0
    # assert token.call().balanceOf(ursula) == 9900
    # assert token.call().balanceOf(alice) == 10000


def test_locked_distribution(web3, chain, token, wallet_manager):
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]
    amount = token.call().balanceOf(creator) // 2
    largest_locked = amount

    # Airdrop
    for miner in web3.eth.accounts[1:]:
        tx = token.transact({'from': creator}).transfer(miner, amount)
        chain.wait.for_receipt(tx)
        amount = amount // 2

    # Lock
    for addr in web3.eth.accounts[1:][::-1]:
        balance = token.call().balanceOf(addr)
        tx = wallet_manager.transact({'from': addr}).createWallet()
        chain.wait.for_receipt(tx)
        wallet = wallet_manager.call().wallets(addr)
        tx = token.transact({'from': addr}).transfer(wallet, balance)
        chain.wait.for_receipt(tx)
        tx = wallet_manager.transact({'from': addr}).lock(balance, 100)
        chain.wait.for_receipt(tx)

    n_locked = wallet_manager.call().getAllLockedTokens()
    assert n_locked > 0

    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, n_locked // 3)
    assert address_stop.lower() == web3.eth.accounts[1].lower()
    assert shift == n_locked // 3

    address_stop, shift = wallet_manager.call().findCumSum(NULL_ADDR, largest_locked)
    assert address_stop.lower() == web3.eth.accounts[2].lower()
    assert shift == 0

    address_stop, shift = wallet_manager.call().findCumSum(
            web3.eth.accounts[2], largest_locked // 2 + 1)
    assert address_stop.lower() == web3.eth.accounts[3].lower()
    assert shift == 1


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
    tx = wallet_manager.transact({'from': ursula}).lock(1000, 100)
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).lock(500, 200)
    chain.wait.for_receipt(tx)

    # Ursula can't use method from Miner contract
    with pytest.raises(TypeError):
        tx = wallet_manager.transact({'from': ursula}).mint(ursula, 1000, 1000, 1000, 1000)
        chain.wait.for_receipt(tx)

    # Ursula and Alice confirm 1 period and mint tokens
    chain.wait.for_block(web3.eth.blockNumber + 50)
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    # Checks that no error
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) > 1000
    assert token.call().balanceOf(alice_wallet.address) > 500
    assert wallet_manager.call().getAllLockedTokens() == 1500

    # Ursula and Alice confirm 2 periods and mint tokens
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    tx = wallet_manager.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = wallet_manager.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 1066
    assert token.call().balanceOf(alice_wallet.address) == 545
    assert wallet_manager.call().getAllLockedTokens() == 500

    # Alice confirm 2 periods and mint tokens
    chain.wait.for_block(web3.eth.blockNumber + 50)
    tx = wallet_manager.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    tx = wallet_manager.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_wallet.address) == 1066
    # Problem with accuracy
    alice_tokens = token.call().balanceOf(alice_wallet.address)
    assert alice_tokens < 633  # max minted tokens
    assert alice_tokens > 583  # min minted tokens
    assert wallet_manager.call().getAllLockedTokens() == 0

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = wallet_manager.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # Ursula can lock some tokens again
    tx = wallet_manager.transact({'from': ursula}).lock(500, 200)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(ursula) == 500
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 100) == 500
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 0
    # And can increase lock
    tx = wallet_manager.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(ursula) == 600
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 100) == 600
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 0
    tx = wallet_manager.transact({'from': ursula}).lock(0, 100)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(ursula) == 600
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 600
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 300) == 0
    tx = wallet_manager.transact({'from': ursula}).lock(100, 100)
    chain.wait.for_receipt(tx)
    assert wallet_manager.call().getLockedTokens(ursula) == 700
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 300) == 700
    assert wallet_manager.call().getLockedTokens(ursula, web3.eth.blockNumber + 400) == 0

    # Alice can withdraw all
    tx = alice_wallet.transact({'from': alice}).withdraw(600)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(alice) == 10100

    # TODO test max confirmed periods
