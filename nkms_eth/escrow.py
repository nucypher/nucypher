from nkms_eth import blockchain
from nkms_eth import token

ESCROW_NAME = 'Escrow'
MINING_COEFF = [10 ** 5, 10 ** 7]


def create():
    """
    Creates an escrow which manages mining
    """
    chain = blockchain.chain()
    creator = chain.web3.eth.accounts[0]  # TODO: make it possible to override
    escrow, tx = chain.provider.get_or_deploy_contract(
        ESCROW_NAME, deploy_args=[token.get().address] + MINING_COEFF,
        deploy_transaction={'from': creator})
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)
    return escrow


def get():
    """
    Returns an escrow object
    """
    return token.get(ESCROW_NAME)
