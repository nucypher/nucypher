from decimal import Decimal, InvalidOperation

import pytest

from nucypher.blockchain.eth.token import TToken


def test_t_token():

    # Alternate construction
    assert TToken(1, "T") == TToken("1.0", "T") == TToken(1.0, "T")

    # Arithmetic

    # TTokens
    one_t = TToken(1, "T")
    zero_t = TToken(0, "T")
    one_hundred_t = TToken(100, "T")
    two_hundred_t = TToken(200, "T")
    three_hundred_t = TToken(300, "T")

    # Nits
    one_t_wei = TToken(1, "TuNit")
    three_t_wei = TToken(3, "TuNit")
    assert three_t_wei.to_tokens() == Decimal("3E-18")
    assert one_t_wei.to_tokens() == Decimal("1E-18")

    # Base Operations
    assert one_hundred_t < two_hundred_t < three_hundred_t
    assert one_hundred_t <= two_hundred_t <= three_hundred_t

    assert three_hundred_t > two_hundred_t > one_hundred_t
    assert three_hundred_t >= two_hundred_t >= one_hundred_t

    assert (one_hundred_t + two_hundred_t) == three_hundred_t
    assert (three_hundred_t - two_hundred_t) == one_hundred_t

    difference = one_t - one_t_wei
    assert not difference == zero_t

    actual = float(difference.to_tokens())
    expected = 0.999999999999999999
    assert actual == expected

    # 3.14 T is 3_140_000_000_000_000_000 TuNit
    pi_tweis = TToken(3.14, "T")
    assert (
        TToken("3.14", "T")
        == pi_tweis.to_units()
        == TToken(3_140_000_000_000_000_000, "TuNit")
    )

    # Mixed type operations
    difference = TToken("3.14159265", "T") - TToken(1.1, "T")
    assert difference == TToken("2.04159265", "T")

    result = difference + one_t_wei
    assert result == TToken(2041592650000000001, "TuNit")

    # Similar to stake read + metadata operations in Staker
    collection = [one_hundred_t, two_hundred_t, three_hundred_t]
    assert (
        sum(collection)
        == TToken("600", "T")
        == TToken(600, "T")
        == TToken(600.0, "T")
        == TToken(600e18, "TuNit")
    )

    #
    # Fractional Inputs
    #

    # A decimal amount of TuNit (i.e., a fraction of a TuNit)
    pi_tweis = TToken("3.14", "TuNit")
    assert pi_tweis == three_t_wei  # Floor

    # A decimal amount of T, which amounts to TuNit with decimals
    pi_ts = TToken("3.14159265358979323846", "T")
    assert pi_ts == TToken(3141592653589793238, "TuNit")  # Floor

    # Positive Infinity
    with pytest.raises(TToken.InvalidAmount):
        _inf = TToken(float("infinity"), "T")

    # Negative Infinity
    with pytest.raises(TToken.InvalidAmount):
        _neg_inf = TToken(float("-infinity"), "T")

    # Not a Number
    with pytest.raises(InvalidOperation):
        _nan = TToken(float("NaN"), "T")

    # Rounding TTokens
    assert round(pi_ts, 2) == TToken("3.14", "T")
    assert round(pi_ts, 1) == TToken("3.1", "T")
    assert round(pi_ts, 0) == round(pi_ts) == TToken("3", "T")
