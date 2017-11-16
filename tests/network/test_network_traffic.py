from apistar.core import Route
from apistar.frameworks.wsgi import WSGIApp as App
from apistar.test import TestClient

from tests.network.test_network_actors import URSULAS

routes = [
    Route('/kFrag/{hrac}', 'POST', URSULAS[0].set_kfrag),
]

app = App(routes=routes)


def test_set_kfrag():
    """
    Testing a view directly.
    """
    response = URSULAS[0].set_kfrag("some_hrac")
    assert response == "something useful"


def test_http_request():
    """
    Testing a view, using the test client.
    """
    client = TestClient(app)
    response = client.get('http://localhost/kFrag/some_hrac')
    assert response.status_code == 200
    assert response.json() == {'message': 'Welcome to API Star!'}
