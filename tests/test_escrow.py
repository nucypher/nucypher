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

    # Ursula transfers some tokens to the escrow
    tx = token.transact({'from': ursula}).transfer(ursula_escrow.address, 1000)
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
    tx = ursula_escrow.transact({'from': human_jury}).withdraw(500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # But Jury can lock
    tx = ursula_escrow.transact({'from': human_jury}).setLock(500)
    chain.wait.for_receipt(tx)

    # And Ursula's withdrawal attepmt won't succeed
    tx = ursula_escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 500
    assert token.call().balanceOf(ursula) == 9500

    # Now Jury unlocks some
    tx = ursula_escrow.transact({'from': human_jury}).setLock(200)
    chain.wait.for_receipt(tx)

    # And Ursula can withdraw
    tx = ursula_escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula_escrow.address) == 400
    assert token.call().balanceOf(ursula) == 9600
