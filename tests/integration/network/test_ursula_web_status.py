import pytest


@pytest.fixture(scope='module')
def ursula(ursulas):
    ursula = ursulas[3]
    return ursula


@pytest.fixture(scope='module')
def client(ursula):
    ursula.rest_app.config.update({"TESTING": True})
    yield ursula.rest_app.test_client()


def test_ursula_html_renders(ursula, client):
    response = client.get('/')
    assert response.status_code == 404, response.data
    response = client.get('/status/')
    assert response.status_code == 200, response.data
    assert b'<!DOCTYPE html>' in response.data
    assert ursula.checksum_address.encode() in response.data
    assert str(ursula.nickname).encode() in response.data


@pytest.mark.parametrize('omit_peers', [False, True])
def test_json_status_endpoint(ursula, client, omit_peers):
    omit_peers_str = 'true' if omit_peers else 'false'
    response = client.get(f'/status/?json=true&omit_peers={omit_peers_str}')
    assert response.status_code == 200
    json_status = response.get_json()
    status = ursula.status_info(omit_peers=omit_peers)
    assert json_status == status.to_json()
