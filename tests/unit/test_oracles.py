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

from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError
from web3 import Web3

from nucypher.utilities.oracles import Oracle, EtherchainGasPriceOracle, UpvestGasPriceOracle


def test_probe_oracle(mocker):

    oracle = Oracle()
    oracle.api_url = "http://foo.bar"

    with patch('requests.get', side_effect=ConnectionError("Bad connection")) as mocked_get:
        with pytest.raises(Oracle.OracleError, match="Bad connection"):
            oracle._probe_oracle()
        mocked_get.assert_called_once_with(oracle.api_url)

    bad_response = mocker.Mock()
    bad_response.status_code = 400
    with patch('requests.get') as mocked_get:
        mocked_get.return_value = bad_response
        with pytest.raises(Oracle.OracleError, match="status code 400"):
            oracle._probe_oracle()
        mocked_get.assert_called_once_with(oracle.api_url)

    json = {'foo': 'bar'}
    good_response = mocker.Mock()
    good_response.status_code = 200
    good_response.json = mocker.Mock(return_value=json)
    with patch('requests.get') as mocked_get:
        mocked_get.return_value = good_response
        oracle._probe_oracle()
        mocked_get.assert_called_once_with(oracle.api_url)
        assert oracle._raw_data == json


def test_etherchain():
    etherchain_json = {
        "safeLow": "99.0",
        "standard": "105.0",
        "fast": "108.0",
        "fastest": "119.9"
    }
    oracle = EtherchainGasPriceOracle()
    with patch.object(oracle, '_probe_oracle'):
        oracle._raw_data = etherchain_json
        assert oracle.get_gas_price('safeLow') == Web3.toWei(99.0, 'gwei')
        assert oracle.get_gas_price('standard') == Web3.toWei(105.0, 'gwei')
        assert oracle.get_gas_price('fast') == Web3.toWei(108.0, 'gwei')
        assert oracle.get_gas_price('fastest') == Web3.toWei(119.9, 'gwei')
        assert oracle.get_gas_price() == oracle.get_gas_price('fast')  # Default


def test_upvest():
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
    oracle = UpvestGasPriceOracle()
    with patch.object(oracle, '_probe_oracle'):
        oracle._raw_data = upvest_json
        assert oracle.get_gas_price('slow') == Web3.toWei(87.19, 'gwei')
        assert oracle.get_gas_price('medium') == Web3.toWei(91.424, 'gwei')
        assert oracle.get_gas_price('fast') == Web3.toWei(97.158, 'gwei')
        assert oracle.get_gas_price('fastest') == Web3.toWei(105.2745, 'gwei')
        assert oracle.get_gas_price() == oracle.get_gas_price('fastest')  # Default
