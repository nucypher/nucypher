from unittest.mock import patch

import pytest
from constant_sorrow.constants import FAST, FASTEST, MEDIUM, SLOW
from requests.exceptions import ConnectionError
from web3 import Web3

from nucypher.utilities.datafeeds import (
    Datafeed,
    EthereumGasPriceDatafeed,
    PolygonGasStationDatafeed,
)

polygon_gas_station = {
    "safeLow": {"maxPriorityFee": 30, "maxFee": 63.35796266},
    "standard": {"maxPriorityFee": 30, "maxFee": 63.35796266},
    "fast": {"maxPriorityFee": 33.890873063, "maxFee": 67.248835723},
    "estimatedBaseFee": 33.35796266,
    "blockTime": 3,
    "blockNumber": 52691632,
}


def test_probe_datafeed(mocker):

    feed = Datafeed()
    feed.api_url = "http://foo.bar"

    with patch(
        "requests.get", side_effect=ConnectionError("Bad connection")
    ) as mocked_get:
        with pytest.raises(Datafeed.DatafeedError, match="Bad connection"):
            feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)

    bad_response = mocker.Mock()
    bad_response.status_code = 400
    with patch("requests.get") as mocked_get:
        mocked_get.return_value = bad_response
        with pytest.raises(Datafeed.DatafeedError, match="status code 400"):
            feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)

    json = {"foo": "bar"}
    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json = mocker.Mock(return_value=json)
    with patch("requests.get") as mocked_get:
        mocked_get.return_value = good_response
        feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)
        assert feed._raw_data == json


def test_canonical_speed_names():
    # Valid speed names, grouped in equivalence classes
    speed_equivalence_classes = {
        SLOW: (
            "slow",
            "SLOW",
            "Slow",
            "safeLow",
            "safelow",
            "SafeLow",
            "SAFELOW",
            "low",
            "LOW",
            "Low",
        ),
        MEDIUM: (
            "medium",
            "MEDIUM",
            "Medium",
            "standard",
            "STANDARD",
            "Standard",
            "average",
            "AVERAGE",
            "Average",
        ),
        FAST: ("fast", "FAST", "Fast", "high", "HIGH", "High"),
        FASTEST: ("fastest", "FASTEST", "Fastest"),
    }

    for canonical_speed, equivalence_class in speed_equivalence_classes.items():
        for speed_name in equivalence_class:
            assert canonical_speed == EthereumGasPriceDatafeed.get_canonical_speed(speed_name)

    # Invalid speed names, but that are somewhat similar to a valid one so we can give a suggestion
    similarities = (
        ("hihg", "high"),
        ("zlow", "low"),
    )

    for wrong_name, suggestion in similarities:
        message = f"'{wrong_name}' is not a valid speed name. Did you mean '{suggestion}'?"
        with pytest.raises(LookupError, match=message):
            EthereumGasPriceDatafeed.get_canonical_speed(wrong_name)

    # Utterly wrong speed names. Shame on you.
    wrong_name = "🙈"
    with pytest.raises(LookupError, match=f"'{wrong_name}' is not a valid speed name."):
        EthereumGasPriceDatafeed.get_canonical_speed(wrong_name)


def test_polygon_gas_station():
    feed = PolygonGasStationDatafeed()

    assert set(feed._speed_names.values()).issubset(polygon_gas_station.keys())
    assert feed._default_speed in polygon_gas_station.keys()

    with patch.object(feed, "_probe_feed"):
        feed._raw_data = polygon_gas_station

        assert feed.get_gas_fee_pricing("safeLow").max_priority_fee == Web3.to_wei(
            30, "gwei"
        )
        assert feed.get_gas_fee_pricing("standard").max_priority_fee == Web3.to_wei(
            30, "gwei"
        )
        assert feed.get_gas_fee_pricing("fast").max_priority_fee == Web3.to_wei(
            33.890873063, "gwei"
        )
        assert feed.get_gas_fee_pricing("fastest").max_priority_fee == Web3.to_wei(
            33.890873063, "gwei"
        )

        assert feed.get_gas_fee_pricing("safeLow").max_fee == Web3.to_wei(
            63.35796266, "gwei"
        )
        assert feed.get_gas_fee_pricing("standard").max_fee == Web3.to_wei(
            63.35796266, "gwei"
        )
        assert feed.get_gas_fee_pricing("fast").max_fee == Web3.to_wei(
            67.248835723, "gwei"
        )
        assert feed.get_gas_fee_pricing("fastest").max_fee == Web3.to_wei(
            67.248835723, "gwei"
        )

        assert feed.get_gas_fee_pricing("safeLow").block == 52691632
        assert feed.get_gas_fee_pricing("standard").block == 52691632
        assert feed.get_gas_fee_pricing("fast").block == 52691632
        assert feed.get_gas_fee_pricing("fastest").block == 52691632

        assert feed.get_gas_fee_pricing() == feed.get_gas_fee_pricing("fast")  # Default
