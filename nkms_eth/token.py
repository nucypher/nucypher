from nkms_eth import blockchain

CONTRACT_NAME = 'HumanStandardToken'  # TODO this should be NuCypher's class
ESCROW_NAME = 'Escrow'
SUBDIGITS = 6
M = 10 ** SUBDIGITS
MINING_COEFF = [10 ** 5, 10 ** 7]
PREMINE = int(1e9) * M
SATURATION = int(1e10) * M


def create():
    """
    Creates a contract with tokens and returns it.
    If it was already created, just returns the already existing contract

    :returns:   Token contract object
    """
    chain = blockchain.chain()
    web3 = chain.web3
    creator = web3.eth.accounts[0]  # TODO: make it possible to override

    token, tx = chain.provider.get_or_deploy_contract(
        CONTRACT_NAME, deploy_args=[
            PREMINE, SATURATION, 'NuCypher KMS', SUBDIGITS, 'KMS'],
        deploy_transaction={
            'from': creator})
    if tx:
        chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)

    return token


def get(name=CONTRACT_NAME):
    """
    Gets an existing contract or returns an error
    """
    return blockchain.chain().provider.get_contract(name)


def create_escrow():
    """
    Creates an escrow which manages mining
    """
    chain = blockchain.chain()
    token = get()
    creator = chain.web3.eth.accounts[0]  # TODO: make it possible to override
    escrow, tx = chain.provider.get_or_deploy_contract(
        ESCROW_NAME, deploy_args=[token.address] + MINING_COEFF,
        deploy_transaction={'from': creator})
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)
    return escrow


def escrow():
    """
    Returns an escrow object
    """
    return get(ESCROW_NAME)


if __name__ == '__main__':
    create()
    get()
