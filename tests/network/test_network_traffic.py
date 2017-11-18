
from apistar.test import TestClient

from tests.network.test_network_actors import URSULAS




def test_set_kfrag():
    response = URSULAS[0].set_kfrag(u"some_hrac")
    assert response == "something useful"


def test_http_request():

    response = client.post('http://localhost/kFrag/some_hrac')
    assert response.status_code == 200
