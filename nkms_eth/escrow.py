import random
from typing import List
from nkms_eth import blockchain
from nkms_eth import token

ESCROW_NAME = 'Escrow'
HOURS_PER_PERIOD = 1  # 24
MIN_RELEASE_PERIODS = 1  # 30
MAX_AWARDED_PERIODS = 365
MINING_COEFF = [
    HOURS_PER_PERIOD,
    2 * 10 ** 7,
    MAX_AWARDED_PERIODS,
    MAX_AWARDED_PERIODS,
    MIN_RELEASE_PERIODS
]
NULL_ADDR = '0x' + '0' * 40


def create():
    """
    Creates an escrow which manages mining
    """
    chain = blockchain.chain()
    creator = chain.web3.eth.accounts[0]  # TODO: make it possible to override
    tok = token.get()
    escrow, tx = chain.provider.get_or_deploy_contract(
        ESCROW_NAME, deploy_args=[token.get().address] + MINING_COEFF,
        deploy_transaction={'from': creator})
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)
    tx = tok.transact({'from': creator}).addMiner(escrow.address)
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)
    return escrow


def get():
    """
    Returns an escrow object
    """
    return token.get(ESCROW_NAME)


def sample(n: int = 10)-> List[str]:
    """
    Select n random staking Ursulas, according to their stake distribution
    The returned addresses are shuffled, so one can request more than needed and
    throw away those which do not respond
    """
    escrow = get()
    n_select = int(n * 1.7)  # Select more ursulas
    n_tokens = escrow.call().getAllLockedTokens()
    duration = 10

    for _ in range(5):  # number of tries
        points = [0] + sorted(random.randrange(n_tokens) for _ in
                              range(n_select))
        deltas = [i - j for i, j in zip(points[1:], points[:-1])]
        addrs = set()
        addr = NULL_ADDR
        shift = 0

        for delta in deltas:
            addr, shift = escrow.call().findCumSum(addr, delta + shift, duration)
            addrs.add(addr)

        if len(addrs) >= n:
            addrs = random.sample(addrs, n)
            return addrs

    raise Exception('Not enough Ursulas')
