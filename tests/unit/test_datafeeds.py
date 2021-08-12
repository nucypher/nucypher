"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from collections import Callable
from statistics import median
from unittest.mock import patch

import pytest
from constant_sorrow.constants import SLOW, MEDIUM, FAST, FASTEST
from requests.exceptions import ConnectionError
from web3 import Web3

from nucypher.utilities.datafeeds import (
    Datafeed,
    EtherchainGasPriceDatafeed,
    EthereumGasPriceDatafeed,
    UpvestGasPriceDatafeed,
    ZoltuGasPriceDatafeed
)
from nucypher.utilities.gas_strategies import construct_datafeed_median_strategy


etherchain_json = {
    "safeLow": "99.0",
    "standard": "105.0",
    "fast": "108.0",
    "fastest": "119.9"
}

upvest_json = {
    "success": True,
    "updated": "2020-08-19T02:38:00.172Z",
    "estimates": {
        "fastest": 105.2745,
        "fast": 97.158,
        "medium": 91.424,
        "slow": 87.19
    }
}

zoltu_json = {
    "number_of_blocks": 200,
    "latest_block_number": 11294588,
    "percentile_1": "1 nanoeth",
    "percentile_2": "1 nanoeth",
    "percentile_3": "3.452271231 nanoeth",
    "percentile_4": "10 nanoeth",
    "percentile_5": "10 nanoeth",
    "percentile_10": "18.15 nanoeth",
    "percentile_15": "25 nanoeth",
    "percentile_20": "28 nanoeth",
    "percentile_25": "30 nanoeth",
    "percentile_30": "32 nanoeth",
    "percentile_35": "37 nanoeth",
    "percentile_40": "41 nanoeth",
    "percentile_45": "44 nanoeth",
    "percentile_50": "47.000001459 nanoeth",
    "percentile_55": "50 nanoeth",
    "percentile_60": "52.5 nanoeth",
    "percentile_65": "55.20000175 nanoeth",
    "percentile_70": "56.1 nanoeth",
    "percentile_75": "58 nanoeth",
    "percentile_80": "60.20000175 nanoeth",
    "percentile_85": "63 nanoeth",
    "percentile_90": "64 nanoeth",
    "percentile_95": "67 nanoeth",
    "percentile_96": "67.32 nanoeth",
    "percentile_97": "68 nanoeth",
    "percentile_98": "70 nanoeth",
    "percentile_99": "71 nanoeth",
    "percentile_100": "74 nanoeth"
}


def test_probe_datafeed(mocker):

    feed = Datafeed()
    feed.api_url = "http://foo.bar"

    with patch('requests.get', side_effect=ConnectionError("Bad connection")) as mocked_get:
        with pytest.raises(Datafeed.DatafeedError, match="Bad connection"):
            feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)

    bad_response = mocker.Mock()
    bad_response.status_code = 400
    with patch('requests.get') as mocked_get:
        mocked_get.return_value = bad_response
        with pytest.raises(Datafeed.DatafeedError, match="status code 400"):
            feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)

    json = {'foo': 'bar'}
    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json = mocker.Mock(return_value=json)
    with patch('requests.get') as mocked_get:
        mocked_get.return_value = good_response
        feed._probe_feed()
        mocked_get.assert_called_once_with(feed.api_url)
        assert feed._raw_data == json


def test_canonical_speed_names():
    # Valid speed names, grouped in equivalence classes
    speed_equivalence_classes = {
        SLOW: ('slow', 'SLOW', 'Slow',
               'safeLow', 'safelow', 'SafeLow', 'SAFELOW',
               'low', 'LOW', 'Low'),
        MEDIUM: ('medium', 'MEDIUM', 'Medium',
                 'standard', 'STANDARD', 'Standard',
                 'average', 'AVERAGE', 'Average'),
        FAST: ('fast', 'FAST', 'Fast',
               'high', 'HIGH', 'High'),
        FASTEST: ('fastest', 'FASTEST', 'Fastest')
    }

    for canonical_speed, equivalence_class in speed_equivalence_classes.items():
        for speed_name in equivalence_class:
            assert canonical_speed == EthereumGasPriceDatafeed.get_canonical_speed(speed_name)

    # Invalid speed names, but that are somewhat similar to a valid one so we can give a suggestion
    similarities = (
        ('hihg', 'high'),
        ('zlow', 'low'),
    )

    for wrong_name, suggestion in similarities:
        message = f"'{wrong_name}' is not a valid speed name. Did you mean '{suggestion}'?"
        with pytest.raises(LookupError, match=message):
            EthereumGasPriceDatafeed.get_canonical_speed(wrong_name)

    # Utterly wrong speed names. Shame on you.
    wrong_name = "🙈"
    with pytest.raises(LookupError, match=f"'{wrong_name}' is not a valid speed name."):
        EthereumGasPriceDatafeed.get_canonical_speed(wrong_name)


def test_etherchain():
    feed = EtherchainGasPriceDatafeed()

    assert set(feed._speed_names.values()).issubset(etherchain_json.keys())
    assert feed._default_speed in etherchain_json.keys()

    with patch.object(feed, '_probe_feed'):
        feed._raw_data = etherchain_json
        assert feed.get_gas_price('safeLow') == Web3.toWei(99.0, 'gwei')
        assert feed.get_gas_price('standard') == Web3.toWei(105.0, 'gwei')
        assert feed.get_gas_price('fast') == Web3.toWei(108.0, 'gwei')
        assert feed.get_gas_price('fastest') == Web3.toWei(119.9, 'gwei')
        assert feed.get_gas_price() == feed.get_gas_price('fast')  # Default
        parsed_gas_prices = feed.gas_prices

    with patch('nucypher.utilities.datafeeds.EtherchainGasPriceDatafeed._parse_gas_prices', autospec=True):
        EtherchainGasPriceDatafeed.gas_prices = dict()
        with patch.dict(EtherchainGasPriceDatafeed.gas_prices, values=parsed_gas_prices):
            gas_strategy = feed.construct_gas_strategy()
            assert gas_strategy("web3", "tx") == Web3.toWei(108.0, 'gwei')


def test_upvest():
    feed = UpvestGasPriceDatafeed()

    assert set(feed._speed_names.values()).issubset(upvest_json['estimates'].keys())
    assert feed._default_speed in upvest_json['estimates'].keys()

    with patch.object(feed, '_probe_feed'):
        feed._raw_data = upvest_json
        assert feed.get_gas_price('slow') == Web3.toWei(87.19, 'gwei')
        assert feed.get_gas_price('medium') == Web3.toWei(91.424, 'gwei')
        assert feed.get_gas_price('fast') == Web3.toWei(97.158, 'gwei')
        assert feed.get_gas_price('fastest') == Web3.toWei(105.2745, 'gwei')
        assert feed.get_gas_price() == feed.get_gas_price('fastest')  # Default
        parsed_gas_prices = feed.gas_prices

    with patch('nucypher.utilities.datafeeds.UpvestGasPriceDatafeed._parse_gas_prices', autospec=True):
        UpvestGasPriceDatafeed.gas_prices = dict()
        with patch.dict(UpvestGasPriceDatafeed.gas_prices, values=parsed_gas_prices):
            gas_strategy = feed.construct_gas_strategy()
            assert gas_strategy("web3", "tx") == Web3.toWei(105.2745, 'gwei')


def test_zoltu():
    feed = ZoltuGasPriceDatafeed()

    assert set(feed._speed_names.values()).issubset(zoltu_json.keys())
    # assert feed._default_speed in zoltu_json.keys()

    with patch.object(feed, '_probe_feed'):
        feed._raw_data = zoltu_json
        assert feed.get_gas_price('slow') == Web3.toWei(41, 'gwei')
        assert feed.get_gas_price('medium') == Web3.toWei(58, 'gwei')
        assert feed.get_gas_price('fast') == Web3.toWei(67, 'gwei')
        assert feed.get_gas_price('fastest') == Web3.toWei(70, 'gwei')
        assert feed.get_gas_price() == feed.get_gas_price('fast')  # Default
        parsed_gas_prices = feed.gas_prices

    with patch('nucypher.utilities.datafeeds.ZoltuGasPriceDatafeed._parse_gas_prices', autospec=True):
        ZoltuGasPriceDatafeed.gas_prices = dict()
        with patch.dict(ZoltuGasPriceDatafeed.gas_prices, values=parsed_gas_prices):
            gas_strategy = feed.construct_gas_strategy()
            assert gas_strategy("web3", "tx") == Web3.toWei(67, 'gwei')


def test_datafeed_median_gas_price_strategy():

    mock_etherchain_gas_price = 1000
    mock_upvest_gas_price = 2000
    mock_zoltu_gas_price = 4000
    mock_rpc_gas_price = 42

    def construct_mock_gas_strategy(gas_price) -> Callable:
        def _mock_gas_strategy(web3, tx=None):
            return gas_price
        return _mock_gas_strategy

    # In normal circumstances, all datafeeds in the strategy work, and the median is returned
    with patch('nucypher.utilities.datafeeds.UpvestGasPriceDatafeed.construct_gas_strategy',
               return_value=construct_mock_gas_strategy(mock_upvest_gas_price)):
        # with patch('nucypher.utilities.datafeeds.EtherchainGasPriceDatafeed.construct_gas_strategy',
        #            return_value=construct_mock_gas_strategy(mock_etherchain_gas_price)):
        with patch('nucypher.utilities.datafeeds.ZoltuGasPriceDatafeed.construct_gas_strategy',
                   return_value=construct_mock_gas_strategy(mock_zoltu_gas_price)):
            datafeed_median_gas_price_strategy = construct_datafeed_median_strategy()
            assert datafeed_median_gas_price_strategy("web3", "tx") == median([mock_upvest_gas_price,
                                                                               mock_zoltu_gas_price])

    # If, for example, Upvest fails, the median is computed using the other two feeds
    with patch('nucypher.utilities.datafeeds.UpvestGasPriceDatafeed._probe_feed',
               side_effect=Datafeed.DatafeedError):
        # with patch('nucypher.utilities.datafeeds.EtherchainGasPriceDatafeed.construct_gas_strategy',
        #            return_value=construct_mock_gas_strategy(mock_etherchain_gas_price)):
        with patch('nucypher.utilities.datafeeds.ZoltuGasPriceDatafeed.construct_gas_strategy',
                   return_value=construct_mock_gas_strategy(mock_zoltu_gas_price)):
            datafeed_median_gas_price_strategy = construct_datafeed_median_strategy()
            assert datafeed_median_gas_price_strategy("web3", "tx") == median([mock_zoltu_gas_price])

    # If only one feed works, then the return value corresponds to this feed
    with patch('nucypher.utilities.datafeeds.UpvestGasPriceDatafeed._probe_feed',
               side_effect=Datafeed.DatafeedError):
        # with patch('nucypher.utilities.datafeeds.EtherchainGasPriceDatafeed._probe_feed',
        #            side_effect=Datafeed.DatafeedError):
        with patch('nucypher.utilities.datafeeds.ZoltuGasPriceDatafeed.construct_gas_strategy',
                   return_value=construct_mock_gas_strategy(mock_zoltu_gas_price)):
            datafeed_median_gas_price_strategy = construct_datafeed_median_strategy()
            assert datafeed_median_gas_price_strategy("web3", "tx") == mock_zoltu_gas_price

    # If all feeds fail, we fallback to the rpc_gas_price_strategy
    # with patch('nucypher.utilities.datafeeds.EtherchainGasPriceDatafeed._probe_feed',
    #            side_effect=Datafeed.DatafeedError):
    with patch('nucypher.utilities.datafeeds.UpvestGasPriceDatafeed._probe_feed',
               side_effect=Datafeed.DatafeedError):
        with patch('nucypher.utilities.datafeeds.ZoltuGasPriceDatafeed._probe_feed',
               side_effect=Datafeed.DatafeedError):
            with patch('nucypher.utilities.gas_strategies.rpc_gas_price_strategy',
                       side_effect=construct_mock_gas_strategy(mock_rpc_gas_price)):
                datafeed_median_gas_price_strategy = construct_datafeed_median_strategy()
                assert datafeed_median_gas_price_strategy("web3", "tx") == mock_rpc_gas_price
