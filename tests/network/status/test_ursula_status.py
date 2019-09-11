import pytest
from flask import Flask

from nucypher.config.characters import UrsulaConfiguration
from nucypher.network.status.status_page import UrsulaStatusPage

#  TODO: Current issue: https://github.com/InstaPy/instapy-quickstart/issues/63
@pytest.mark.skip("Issues with compatibility with latest Chrome version")
def test_render_lonely_ursula_status_page(dash_duo):
    ursula_config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    ursula = ursula_config()

    server = Flask("ursula-status")
    status_page = UrsulaStatusPage(ursula=ursula,
                                   title=ursula.nickname,
                                   flask_server=server,
                                   route_url='/')

    dash_duo.start_server(status_page.dash_app)

    title = dash_duo.find_element_by_id("status-title").text
    assert title == ursula.nickname


#  TODO: Current issue: https://github.com/InstaPy/instapy-quickstart/issues/63
@pytest.mark.skip("Issues with compatibility with latest Chrome version")
def test_render_ursula_status_page_with_known_nodes(federated_ursulas, dash_duo):
    ursula_config = UrsulaConfiguration(dev_mode=True, federated_only=True, known_nodes=federated_ursulas)
    ursula = ursula_config()

    server = Flask("ursula-status")
    status_page = UrsulaStatusPage(ursula=ursula,
                                   title=ursula.nickname,
                                   flask_server=server,
                                   route_url='/')
    dash_duo.start_server(status_page.dash_app)
    title = dash_duo.find_element_by_id("status-title").text
    assert title == ursula.nickname

    # TODO: fix ui testing to use dash[testing]
    # node_table = dash_duo.wait_for_element_by_id(dash_driver, 'node-table', 10)  # wait for maximum 10s
    # node_table_info = node_table.get_attribute('innerHTML')
    #
    # # Every known nodes address is rendered
    # for known_ursula in federated_ursulas:
    #     assert known_ursula.checksum_address[:10] in node_table_info
    #     assert known_ursula.nickname in node_table_info
    #     assert known_ursula.rest_url() in node_table_info
