
import itertools

from web3 import Web3

from nucypher.utilities.gas_strategies import (
    construct_fixed_price_gas_strategy,
    max_price_gas_strategy_wrapper
)


def test_fixed_price_gas_strategy():

    strategy = construct_fixed_price_gas_strategy(gas_price=42)

    assert 42 == strategy("web3", "tx")
    assert 42 == strategy("web3", "tx")
    assert 42 == strategy("web3", "tx")
    assert "0gwei" == strategy.name

    strategy = construct_fixed_price_gas_strategy(gas_price=12.34, denomination="gwei")

    assert 12340000000 == strategy("web3", "tx")
    assert 12340000000 == strategy("web3", "tx")
    assert 12340000000 == strategy("web3", "tx")
    assert "12gwei" == strategy.name


def test_max_price_gas_strategy(mocker, monkeypatch):

    gas_prices_gwei = [10, 100, 999, 1000, 1001, 1_000_000, 1_000_000_000]
    gas_prices_wei = [Web3.to_wei(gwei_price, 'gwei') for gwei_price in gas_prices_gwei]
    max_gas_price_gwei = 1000
    max_gas_price_wei = Web3.to_wei(max_gas_price_gwei, 'gwei')
    mock_gas_strategy = mocker.Mock(side_effect=itertools.cycle(gas_prices_wei))

    wrapped_strategy = max_price_gas_strategy_wrapper(gas_strategy=mock_gas_strategy,
                                                      max_gas_price_wei=max_gas_price_wei)

    for price in gas_prices_wei[:4]:
        assert wrapped_strategy("web3", "tx") == price
        assert price <= max_gas_price_wei

    for _ in gas_prices_wei[4:]:
        assert wrapped_strategy("web3", "tx") == max_gas_price_wei
