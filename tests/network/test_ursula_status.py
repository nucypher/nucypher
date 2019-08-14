from nucypher.config.characters import UrsulaConfiguration
from nucypher.network.server import status_template


def test_render_lonely_ursula_status_page(tmpdir):
    ursula_config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    ursula = ursula_config()

    rendering = status_template.render(this_node=ursula, known_nodes=ursula.known_nodes)
    assert '<!DOCTYPE html>' in rendering
    assert ursula.nickname in rendering


def test_render_ursula_status_page_with_known_nodes(tmpdir, federated_ursulas):
    ursula_config = UrsulaConfiguration(dev_mode=True, federated_only=True, known_nodes=federated_ursulas)
    ursula = ursula_config()

    rendering = status_template.render(this_node=ursula, known_nodes=ursula.known_nodes)
    assert '<!DOCTYPE html>' in rendering
    assert ursula.nickname in rendering

    # Every known nodes staker_address is rendered
    for known_ursula in federated_ursulas:
        assert known_ursula.checksum_address in rendering
