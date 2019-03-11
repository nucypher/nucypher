import json
import re
from base64 import b64decode, b64encode

import responses
from pytest_dash import wait_for
from pytest_dash.application_runners import import_app
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower

ALICE_URL = "http://localhost:8151"
ENRICO_URL = "http://localhost:5151"


class wait_for_non_empty_text(object):
    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        element = driver.find_element(*self.locator)
        if element.text != '':
            return element
        else:
            return False


@responses.activate
def test_heartbeat_rest_ui_demo_lifecycle(dash_threaded,
                                          alice_control_test_client,
                                          enrico_control_test_client,
                                          federated_alice,
                                          federated_bob):
    driver = dash_threaded.driver

    dash_app = import_app('examples.heartbeat_rest_ui.char_control_heartbeat', application_name='app')
    dash_threaded(dash_app)

    ##########################
    # setup endpoint responses
    ##########################
    ## '/derive_policy_encrypting_key'
    def derive_key_callback(request):
        label = request.url[request.url.rfind('/')+1:]
        derive_response = alice_control_test_client.post(f'/derive_policy_encrypting_key/{label}')
        return (derive_response.status_code,
                derive_response.headers,
                derive_response.data)

    responses.add_callback(responses.POST,
                           url=re.compile(f'{ALICE_URL}/derive_policy_encrypting_key/.*', re.IGNORECASE),
                           callback=derive_key_callback,
                           content_type='application/json')

    ## '/encrypt_message'
    def encrypt_message_callback(request):
        encrypt_response = enrico_control_test_client.post('/encrypt_message', data=request.body)
        return (encrypt_response.status_code,
                encrypt_response.headers,
                encrypt_response.data)

    responses.add_callback(responses.POST,
                           url=re.compile(f'{ENRICO_URL}/encrypt_message', re.IGNORECASE),
                           callback=encrypt_message_callback,
                           content_type='application/json')

    ## '/grant'
    def grant_callback(request):
        grant_response = alice_control_test_client.put('/grant', data=request.body)
        return (grant_response.status_code,
                grant_response.headers,
                grant_response.data)

    responses.add_callback(responses.PUT,
                           url=re.compile(f'{ALICE_URL}/grant', re.IGNORECASE),
                           callback=grant_callback,
                           content_type='application/json')

    ##########################

    # open alicia tab
    alicia_link = driver.find_element_by_link_text('ALICIA')
    alicia_link.click()

    # open enrico tab
    enrico_link = driver.find_element_by_link_text('ENRICO (HEART_MONITOR)')
    enrico_link.click()

    # open bob tab
    bob_link = driver.find_element_by_link_text('BOB')
    bob_link.click()

    ######################
    # switch to alicia tab
    ######################
    driver.switch_to.window('_alicia')

    # derive label and policy key
    create_policy_button = wait_for.wait_for_element_by_css_selector(driver, '#create-policy-button')
    create_policy_button.click()

    # wait for response
    policy_key_element = WebDriverWait(driver, 10).until(
        wait_for_non_empty_text((By.ID, 'policy-enc-key'))
    )
    policy_label_element = driver.find_element_by_id('policy-label')

    # test results
    assert 1 == len(responses.calls)

    request_url = responses.calls[0].request.url
    assert 'derive_policy_encrypting_key' in request_url

    policy_label = request_url[request_url.rfind('/')+1:]
    assert policy_label == policy_label_element.text

    response_json = responses.calls[0].response.text
    response_data = json.loads(response_json)
    derived_policy_key = response_data['result']['policy_encrypting_key']
    assert derived_policy_key == policy_key_element.text

    ######################
    # switch to enrico tab
    ######################
    driver.switch_to.window('_enrico')

    start_monitoring_button = wait_for.wait_for_element_by_css_selector(driver, "#generate-button")
    start_monitoring_button.click()

    # wait for response
    last_heartbeat_element = WebDriverWait(driver, 5).until(
        wait_for_non_empty_text((By.ID, 'cached-last-heartbeat'))
    )
    # verify that actual number
    assert int(last_heartbeat_element.text)

    # test results
    assert 2 <= len(responses.calls)  # derive then at least one encrypt message
    request_url = responses.calls[1].request.url
    assert 'encrypt_message' in request_url

    response_json = responses.calls[1].response.text
    print(response_json)
    response_data = json.loads(response_json)
    message_kit = response_data['result']['message_kit']
    assert UmbralMessageKit.from_bytes(b64decode(message_kit))

    ######################
    # switch to alicia tab
    ######################
    driver.switch_to.window('_alicia')

    # grant access to bob
    #m_threshold_element = driver.find_element_by_id('m-value')
    #m_threshold_element.send_keys(Keys.ARROW_UP)  # 1 -> 2

    #n_shares_element = driver.find_element_by_id('n-value')
    #n_shares_element.send_keys(Keys.ARROW_UP)  # 1 -> 2
    #n_shares_element.send_keys(Keys.ARROW_UP)  # 2 -> 3

    bob_encrypting_key_hex = bytes(federated_bob.public_keys(DecryptingPower)).hex()
    bob_signing_key_hex = bytes(federated_bob.stamp).hex()

    bob_signing_key_element = driver.find_element_by_id('recipient-sig-key-grant')
    bob_signing_key_element.send_keys(bob_signing_key_hex)

    bob_encrypting_key_element = driver.find_element_by_id('recipient-enc-key-grant')
    bob_encrypting_key_element.send_keys(bob_encrypting_key_hex)

    grant_button = driver.find_element_by_id('grant-button')
    grant_button.click()

    # wait for response
    grant_response_element = WebDriverWait(driver, 10).until(
        wait_for_non_empty_text((By.ID, 'grant-response'))
    )

    assert "granted to recipient" in grant_response_element.text
    assert policy_label in grant_response_element.text
    assert bob_encrypting_key_hex in grant_response_element.text
    assert "> ERROR" not in grant_response_element.text
    assert "status code" not in grant_response_element.text
