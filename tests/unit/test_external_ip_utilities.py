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

from nucypher.acumen.perception import FleetSensor
from nucypher.characters.lawful import Ursula
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import NucypherMiddlewareClient
from nucypher.network.nodes import TEACHER_NODES
from nucypher.utilities.networking import (
    determine_external_ip_address,
    get_external_ip_from_centralized_source,
    get_external_ip_from_default_teacher,
    get_external_ip_from_known_nodes,
    CENTRALIZED_IP_ORACLE_URL,
    UnknownIPAddress
)
from tests.constants import MOCK_IP_ADDRESS

MOCK_NETWORK = 'holodeck'


class Dummy:  # Teacher

    def __init__(self, checksum_address):
        self.checksum_address = checksum_address
        self.certificate_filepath = None
        self.domain = MOCK_NETWORK

    class GoodResponse:
        status_code = 200
        text = MOCK_IP_ADDRESS

    class BadResponse:
        status_code = 404
        text = None
        content = 'DUMMY 404'

    def mature(self):
        return self

    def verify_node(self, *args, **kwargs):
        pass

    def rest_url(self):
        return MOCK_IP_ADDRESS

    def metadata(self):
        return self.checksum_address.encode()


@pytest.fixture(autouse=True)
def mock_requests(mocker):
    """prevents making live HTTP requests from this module"""
    make_request = 'nucypher.utilities.networking._request'
    yield mocker.patch(make_request, return_value=None)


@pytest.fixture(autouse=True)
def mock_client(mocker):
    yield mocker.patch.object(NucypherMiddlewareClient, 'invoke_method', return_value=Dummy.GoodResponse)


@pytest.fixture(autouse=True)
def mock_default_teachers(mocker):
    teachers = {MOCK_NETWORK: (MOCK_IP_ADDRESS, )}
    mocker.patch.dict(TEACHER_NODES, teachers, clear=True)


def test_get_external_ip_from_centralized_source(mock_requests):
    get_external_ip_from_centralized_source()
    mock_requests.assert_called_once_with(url=CENTRALIZED_IP_ORACLE_URL)


def test_get_external_ip_from_empty_known_nodes(mock_requests):
    sensor = FleetSensor(domain=MOCK_NETWORK)
    assert len(sensor) == 0
    get_external_ip_from_known_nodes(known_nodes=sensor)
    # skipped because there are no known nodes
    mock_requests.assert_not_called()


def test_get_external_ip_from_known_nodes_with_one_known_node(mock_requests):
    sensor = FleetSensor(domain=MOCK_NETWORK)
    sensor.record_node(Dummy('0xdeadbeef'))
    sensor.record_fleet_state()
    assert len(sensor) == 1
    get_external_ip_from_known_nodes(known_nodes=sensor)
    # skipped because there are too few known nodes
    mock_requests.assert_not_called()


def test_get_external_ip_from_known_nodes(mock_client):

    # Setup FleetSensor
    sensor = FleetSensor(domain=MOCK_NETWORK)
    sample_size = 3
    sensor.record_node(Dummy('0xdeadbeef'))
    sensor.record_node(Dummy('0xdeadllama'))
    sensor.record_node(Dummy('0xdeadmouse'))
    sensor.record_fleet_state()
    assert len(sensor) == sample_size

    # First sampled node replies
    get_external_ip_from_known_nodes(known_nodes=sensor, sample_size=sample_size)
    assert mock_client.call_count == 1
    mock_client.call_count = 0  # reset

    # All sampled nodes dont respond
    mock_client.return_value = Dummy.BadResponse
    get_external_ip_from_known_nodes(known_nodes=sensor, sample_size=sample_size)
    assert mock_client.call_count == sample_size


def test_get_external_ip_from_known_nodes_client(mocker, mock_client):

    # Setup FleetSensor
    sensor = FleetSensor(domain=MOCK_NETWORK)
    sample_size = 3
    sensor.record_node(Dummy('0xdeadbeef'))
    sensor.record_node(Dummy('0xdeadllama'))
    sensor.record_node(Dummy('0xdeadmouse'))
    sensor.record_fleet_state()
    assert len(sensor) == sample_size

    # Setup HTTP Client
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=Dummy('0xdeadpork'))
    teacher_uri = TEACHER_NODES[MOCK_NETWORK][0]

    get_external_ip_from_known_nodes(known_nodes=sensor, sample_size=sample_size)
    assert mock_client.call_count == 1  # first node responded

    function, endpoint = mock_client.call_args[0]
    assert function.__name__ == 'get'
    assert endpoint == f'https://{teacher_uri}/ping'


def test_get_external_ip_default_teacher_unreachable(mocker):
    for error in NodeSeemsToBeDown:
        # Default seednode is down
        mocker.patch.object(Ursula, 'from_teacher_uri', side_effect=error)
        ip = get_external_ip_from_default_teacher(network=MOCK_NETWORK)
        assert ip is None


def test_get_external_ip_from_default_teacher(mocker, mock_client, mock_requests):

    mock_client.return_value = Dummy.GoodResponse
    teacher_uri = TEACHER_NODES[MOCK_NETWORK][0]
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=Dummy('0xdeadbeef'))

    # "Success"
    ip = get_external_ip_from_default_teacher(network=MOCK_NETWORK)
    assert ip == MOCK_IP_ADDRESS

    # Check that the correct endpoint and function is targeted
    mock_requests.assert_not_called()
    mock_client.assert_called_once()
    function, endpoint = mock_client.call_args[0]
    assert function.__name__ == 'get'
    assert endpoint == f'https://{teacher_uri}/ping'


def test_get_external_ip_default_unknown_network():
    unknown_domain = 'thisisnotarealdomain'

    # Without fleet sensor
    with pytest.raises(UnknownIPAddress):
        determine_external_ip_address(network=unknown_domain)

    # with fleet sensor
    sensor = FleetSensor(domain=unknown_domain)
    with pytest.raises(UnknownIPAddress):
        determine_external_ip_address(known_nodes=sensor, network=unknown_domain)


def test_get_external_ip_cascade_failure(mocker, mock_requests):
    first = mocker.patch('nucypher.utilities.networking.get_external_ip_from_known_nodes', return_value=None)
    second = mocker.patch('nucypher.utilities.networking.get_external_ip_from_default_teacher', return_value=None)
    third = mocker.patch('nucypher.utilities.networking.get_external_ip_from_centralized_source', return_value=None)

    sensor = FleetSensor(domain=MOCK_NETWORK)
    sensor.record_node(Dummy('0xdeadbeef'))
    sensor.record_fleet_state()

    with pytest.raises(UnknownIPAddress, match='External IP address detection failed'):
        determine_external_ip_address(network=MOCK_NETWORK, known_nodes=sensor)

    first.assert_called_once()
    second.assert_called_once()
    third.assert_called_once()
