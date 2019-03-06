import pytest
import re
import json

import responses
from pytest_dash.application_runners import import_app
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

from pytest_dash import wait_for


class wait_for_non_empty_text(object):
    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        element = driver.find_element(*self.locator)
        if element.text != '':
            return element
        else:
            return False


ALICE_URL = "http://localhost:8151"


@responses.activate
def test_alicia_derive_policy_pubkey(dash_threaded, alice_control_test_client):
    driver = dash_threaded.driver

    dash_app = import_app('examples.heartbeat_rest_ui.char_control_heartbeat', application_name='app')
    dash_threaded(dash_app)

    def request_callback(request):
        label = request.url[request.url.rfind('/')+1:]
        derive_response = alice_control_test_client.post(f'/derive_policy_pubkey/{label}')
        return (derive_response.status_code,
                derive_response.headers,
                derive_response.data)

    # setup fake REST responses
    responses.add_callback(responses.POST,
                           url=re.compile(f'{ALICE_URL}/derive_policy_pubkey/.*', re.IGNORECASE),
                           callback=request_callback,
                           content_type='application/json')

    # open alicia tab
    alicia_link = driver.find_element_by_link_text('ALICIA')
    alicia_link.click()

    # switch to alicia tab
    driver.switch_to.window('_alicia')

    create_policy_button = wait_for.wait_for_element_by_css_selector(driver, '#create-policy-button')
    create_policy_button.click()

    # wait for derive key request-response dance to occur
    policy_key = WebDriverWait(driver, 10).until(
        wait_for_non_empty_text((By.ID, 'policy-enc-key'))
    )
    policy_label = driver.find_element_by_id('policy-label')

    assert 1 == len(responses.calls)

    request_url = responses.calls[0].request.url
    assert 'derive_policy_pubkey' in request_url

    request_label = request_url[request_url.rfind('/')+1:]
    assert request_label == policy_label.text

    response_json = responses.calls[0].response.text
    response_data = json.loads(response_json)
    derived_key = response_data['result']['policy_encrypting_key']

    assert derived_key == policy_key.text
