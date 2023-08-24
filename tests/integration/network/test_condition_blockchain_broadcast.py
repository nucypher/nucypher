import pytest


@pytest.fixture(scope="module")
def multichain_ursula(multichain_ursulas):
    ursula = multichain_ursulas[3]
    return ursula


@pytest.fixture(scope="module")
def client(multichain_ursula):
    multichain_ursula.rest_app.config.update({"TESTING": True})
    yield multichain_ursula.rest_app.test_client()


def test_condition_chains_endpoint_multichain(
    multichain_ursula, client, multichain_ids
):
    response = client.get("/condition_chains")
    assert response.status_code == 200
    expected_payload = {"version": 1.0, "evm": multichain_ids}
    assert response.get_json() == expected_payload
