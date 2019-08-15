from decimal import InvalidOperation, Decimal

import pytest
from web3 import Web3

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_NU(token_economics):

    # Starting Small
    min_allowed_locked = NU(token_economics.minimum_allowed_locked, 'NuNit')
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked.to_nunits())

    min_NU_locked = int(str(token_economics.minimum_allowed_locked)[0:-18])
    expected = NU(min_NU_locked, 'NU')
    assert min_allowed_locked == expected

    # Starting Big
    min_allowed_locked = NU(min_NU_locked, 'NU')
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked)
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked.to_nunits())
    assert str(min_allowed_locked) == '15000 NU'

    # Alternate construction
    assert NU(1, 'NU') == NU('1.0', 'NU') == NU(1.0, 'NU')

    # Arithmetic

    # NUs
    one_nu = NU(1, 'NU')
    zero_nu = NU(0, 'NU')
    one_hundred_nu = NU(100, 'NU')
    two_hundred_nu = NU(200, 'NU')
    three_hundred_nu = NU(300, 'NU')

    # Nits
    one_nu_wei = NU(1, 'NuNit')
    three_nu_wei = NU(3, 'NuNit')
    assert three_nu_wei.to_tokens() == Decimal('3E-18')
    assert one_nu_wei.to_tokens() == Decimal('1E-18')

    # Base Operations
    assert one_hundred_nu < two_hundred_nu < three_hundred_nu
    assert one_hundred_nu <= two_hundred_nu <= three_hundred_nu

    assert three_hundred_nu > two_hundred_nu > one_hundred_nu
    assert three_hundred_nu >= two_hundred_nu >= one_hundred_nu

    assert (one_hundred_nu + two_hundred_nu) == three_hundred_nu
    assert (three_hundred_nu - two_hundred_nu) == one_hundred_nu

    difference = one_nu - one_nu_wei
    assert not difference == zero_nu

    actual = float(difference.to_tokens())
    expected = 0.999999999999999999
    assert actual == expected

    # 3.14 NU is 3_140_000_000_000_000_000 NuNit
    pi_nuweis = NU(3.14, 'NU')
    assert NU('3.14', 'NU') == pi_nuweis.to_nunits() == NU(3_140_000_000_000_000_000, 'NuNit')

    # Mixed type operations
    difference = NU('3.14159265', 'NU') - NU(1.1, 'NU')
    assert difference == NU('2.04159265', 'NU')

    result = difference + one_nu_wei
    assert result == NU(2041592650000000001, 'NuNit')

    # Similar to stake read + metadata operations in Staker
    collection = [one_hundred_nu, two_hundred_nu, three_hundred_nu]
    assert sum(collection) == NU('600', 'NU') == NU(600, 'NU') == NU(600.0, 'NU') == NU(600e+18, 'NuNit')

    #
    # Fractional Inputs
    #

    # A decimal amount of NuNit (i.e., a fraction of a NuNit)
    pi_nuweis = NU('3.14', 'NuNit')
    assert pi_nuweis == three_nu_wei  # Floor

    # A decimal amount of NU, which amounts to NuNit with decimals
    pi_nus = NU('3.14159265358979323846', 'NU')
    assert pi_nus == NU(3141592653589793238, 'NuNit')  # Floor

    # Positive Infinity
    with pytest.raises(NU.InvalidAmount):
        _inf = NU(float('infinity'), 'NU')

    # Negative Infinity
    with pytest.raises(NU.InvalidAmount):
        _neg_inf = NU(float('-infinity'), 'NU')

    # Not a Number
    with pytest.raises(InvalidOperation):
        _nan = NU(float('NaN'), 'NU')


def test_stake(testerchain, agency):
    token_agent, staking_agent, _policy_agent = agency

    class FakeUrsula:
        token_agent, staking_agent, _policy_agent = agency

        burner_wallet = Web3().eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)
        checksum_address = burner_wallet.address
        staking_agent = staking_agent
        token_agent = token_agent
        blockchain = testerchain
        economics = TokenEconomics()

    ursula = FakeUrsula()
    stake = Stake(checksum_address=ursula.checksum_address,
                  first_locked_period=1,
                  last_locked_period=100,
                  value=NU(100, 'NU'),
                  index=0,
                  staking_agent=staking_agent)

    assert stake.value, 'NU' == NU(100, 'NU')

    assert isinstance(stake.time_remaining(), int)      # seconds
    slang_remaining = stake.time_remaining(slang=True)  # words
    assert isinstance(slang_remaining, str)


def test_stake_integration(stakers):
    staker = list(stakers)[1]
    stakes = staker.stakes
    assert stakes

    stake = stakes[0]
    stake.sync()

    blockchain_stakes = staker.staking_agent.get_all_stakes(staker_address=staker.checksum_address)

    stake_info = (stake.first_locked_period, stake.last_locked_period, int(stake.value))
    published_stake_info = list(blockchain_stakes)[0]
    assert stake_info == published_stake_info
    assert stake_info == stake.to_stake_info()
