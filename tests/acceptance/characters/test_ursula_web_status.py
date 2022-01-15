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

import os
from pathlib import Path

import pytest
import tempfile


@pytest.fixture(scope='module')
def ursula(blockchain_ursulas):
    ursula = blockchain_ursulas.pop()
    return ursula


@pytest.fixture(scope='module')
def client(ursula):
    db_fd, db_path = tempfile.mkstemp()
    ursula.rest_app.config['DATABASE'] = Path(db_path)
    ursula.rest_app.config['TESTING'] = True
    with ursula.rest_app.test_client() as client:
        yield client
    os.close(db_fd)
    ursula.rest_app.config['DATABASE'].unlink()


def test_ursula_html_renders(ursula, client):
    response = client.get('/')
    assert response.status_code == 404
    response = client.get('/status/')
    assert response.status_code == 200
    assert b'<!DOCTYPE html>' in response.data
    assert ursula.checksum_address.encode() in response.data
    assert str(ursula.nickname).encode() in response.data


@pytest.mark.parametrize('omit_known_nodes', [False, True])
def test_decentralized_json_status_endpoint(ursula, client, omit_known_nodes):
    omit_known_nodes_str = 'true' if omit_known_nodes else 'false'
    response = client.get(f'/status/?json=true&omit_known_nodes={omit_known_nodes_str}')
    assert response.status_code == 200
    json_status = response.get_json()
    status = ursula.status_info(omit_known_nodes=omit_known_nodes)
    assert json_status == status.to_json()
