from apistar.core import Route
from apistar.frameworks.wsgi import WSGIApp as App
from apistar.test import TestClient

from tests.network.test_network_actors import URSULAS

routes = [
    Route('/kFrag/{hrac}', 'POST', URSULAS[0].set_kfrag),
]

app = App(routes=routes)


def test_set_kfrag():
    response = URSULAS[0].set_kfrag(u"some_hrac")
    assert response == "something useful"


def test_http_request():
    client = TestClient(app)
    response = client.post('http://localhost/kFrag/some_hrac')
    assert response.status_code == 200
