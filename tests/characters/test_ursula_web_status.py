import os
import tempfile

import pytest


@pytest.fixture(scope='module')
def ursula(blockchain_ursulas):
    ursula = blockchain_ursulas.pop()
    return ursula


@pytest.fixture(scope='module')
def client(ursula):
    db_fd, ursula.rest_app.config['DATABASE'] = tempfile.mkstemp()
    ursula.rest_app.config['TESTING'] = True
    with ursula.rest_app.test_client() as client:
        yield client
    os.close(db_fd)
    os.unlink(ursula.rest_app.config['DATABASE'])


def test_ursula_html_renders(ursula, client):
    response = client.get('/')
    assert response.status_code == 404
    response = client.get('/status/')
    assert response.status_code == 200
    assert b'<!DOCTYPE html>' in response.data
    assert ursula.checksum_address.encode() in response.data
    assert ursula.nickname.encode() in response.data


def test_decentralized_json_status_endpoint(ursula, client):
    response = client.get('/status/?json=true')
    assert response.status_code == 200
    json_status = response.get_json()
    status = ursula.abridged_node_details()
    assert json_status == status
