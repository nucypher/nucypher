def test_create_token(web3, chain):
    creator = web3.eth.accounts[1]

    # Create an ERC20 token
    token, txhash = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                10 ** 9, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={
                'from': creator})
    assert txhash is not None

    # Check balance of our (test) account which created the token
    # We created the token using coinbase account
    # Other accounts pre-loaded with ethers are at:
    # web3.eth.accounts
    assert token.call().balanceOf(creator) == 10 ** 9
    assert token.call().balanceOf(web3.eth.accounts[0]) == 0

    assert token.call().name() == 'NuCypher KMS'
    assert token.call().decimals() == 6
    assert token.call().symbol() == 'KMS'
