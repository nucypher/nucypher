import pytest

from nucypher.blockchain.eth.actors import Staker
from tests.utils.blockchain import token_airdrop
from tests.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT


@pytest.fixture(scope='module')
def staker(testerchain, agency, test_registry):
    token_agent, staking_agent, policy_agent = agency
    origin, staker_account, *everybody_else = testerchain.client.accounts
    token_airdrop(token_agent=token_agent,
                  origin=testerchain.etherbase_account,
                  addresses=[staker_account],
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
    staker = Staker(checksum_address=staker_account, is_me=True, registry=test_registry)
    return staker
