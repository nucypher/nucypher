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

import pytest

from tests.constants import MOCK_IP_ADDRESS
from nucypher.characters.lawful import Ursula
from nucypher.acumen.perception import FleetSensor
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.network.middleware import RestMiddleware, NucypherMiddlewareClient
from nucypher.utilities.networking import (
    determine_external_ip_address,
    get_external_ip_from_centralized_source,
    get_external_ip_from_default_teacher,
    get_external_ip_from_known_nodes,
    CENTRALIZED_IP_ORACLE_URL,
    UnknownIPAddress
)


@pytest.fixture(autouse=True)
def mock_requests(mocker):
    make_request = 'nucypher.utilities.networking._request'
    yield mocker.patch(make_request, return_value=None)


def test_get_external_ip_from_centralized_source(mock_requests):
    get_external_ip_from_centralized_source()
    mock_requests.assert_called_once_with(url=CENTRALIZED_IP_ORACLE_URL)


def test_get_external_ip_from_empty_known_nodes(mock_requests):
    sensor = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(sensor) == 0
    get_external_ip_from_known_nodes(known_nodes=sensor)
    mock_requests.assert_not_called()  # skipped because there are no known nodes


def test_get_external_ip_from_default_teacher(mock_requests, mocker):
    network = 'mainnet'
    teacher_uri = RestMiddleware.TEACHER_NODES[network][0]

    class FakeTeacher:
        certificate_filepath = None

        def mature(self):
            return FakeTeacher()

        def verify_node(self, *args, **kwargs):
            pass

        def rest_url(self):
            return teacher_uri

    class MockResponse:
        status_code = 200
        text = MOCK_IP_ADDRESS

        def __int__(self):
            return self.status_code

    mock_client = mocker.patch.object(NucypherMiddlewareClient, 'invoke_method', return_value=MockResponse)
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=FakeTeacher())

    ip = get_external_ip_from_default_teacher(network=network)
    assert ip == MOCK_IP_ADDRESS
    mock_requests.assert_not_called()
    assert mock_client.call_args[0][0].__name__ == 'get'
    assert mock_client.call_args[0][1] == 'https://' + '/'.join((teacher_uri, 'ping'))


def test_failure_to_determine_external_ip_address(mocker):
    sensor = FleetSensor(domain=TEMPORARY_DOMAIN)
    with pytest.raises(UnknownIPAddress):
        determine_external_ip_address(known_nodes=sensor, network=TEMPORARY_DOMAIN)
