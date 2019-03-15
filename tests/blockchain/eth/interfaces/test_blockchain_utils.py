from web3 import Web3

from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED
from nucypher.blockchain.eth.utils import NU, Stake
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_NU():

    # Starting Small
    min_allowed_locked = NU(MIN_ALLOWED_LOCKED, 'NUWei')
    assert MIN_ALLOWED_LOCKED == int(min_allowed_locked.to_nu_wei())

    min_NU_locked = int(str(MIN_ALLOWED_LOCKED)[0:-18])
    expected = NU(min_NU_locked, 'NU')
    assert min_allowed_locked == expected

    # Starting Big
    min_allowed_locked = NU(min_NU_locked, 'NU')
    assert MIN_ALLOWED_LOCKED == int(min_allowed_locked)
    assert MIN_ALLOWED_LOCKED == int(min_allowed_locked.to_nu_wei())

    assert str(min_allowed_locked) == '15000 NU'


def test_stake():

    class FakeUrsula:
        burner_wallet = Web3().eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)
        checksum_public_address = burner_wallet.address
        miner_agent = None

    ursula = FakeUrsula()
    stake = Stake(owner_address=ursula.checksum_public_address,
                  start_period=1,
                  end_period=100,
                  value=NU(100, 'NU'),
                  index=0)

    assert len(stake.id) == 16
    assert stake.value, 'NU' == NU(100, 'NU')

    assert isinstance(stake.time_remaining(), int)      # seconds
    slang_remaining = stake.time_remaining(slang=True)  # words
    assert isinstance(slang_remaining, str)

    one_hundred_nu = NU(100, 'NU')
    two_hundred_nu = NU(200, 'NU')
    three_hundred_nu = NU(300, 'NU')

    assert one_hundred_nu < two_hundred_nu < three_hundred_nu
    assert one_hundred_nu <= two_hundred_nu <= three_hundred_nu

    assert three_hundred_nu > two_hundred_nu > one_hundred_nu
    assert three_hundred_nu >= two_hundred_nu >= one_hundred_nu

    assert (one_hundred_nu + two_hundred_nu) == three_hundred_nu
    assert (three_hundred_nu - two_hundred_nu) == one_hundred_nu


def test_stake_integration(blockchain_ursulas):
    staking_ursula = list(blockchain_ursulas)[1]
    stakes = staking_ursula.stakes
    assert stakes

    stake = stakes[0]
    blockchain_stakes = staking_ursula.miner_agent.get_all_stakes(miner_address=staking_ursula.checksum_public_address)

    stake_info = (stake.start_period, stake.end_period, int(stake.value))
    published_stake_info = list(blockchain_stakes)[0]
    assert stake_info == published_stake_info == stake.to_stake_info()
