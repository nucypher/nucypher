import json
import os

import pytest
from pytest_dash import wait_for
from pytest_dash.application_runners import import_app
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from umbral.keys import UmbralPublicKey, UmbralPrivateKey

WAIT_TIMEOUT_SECS = 15


@pytest.fixture(scope='module')
def dash_app(federated_ursulas):
    # get port of a test federated ursula and set env variable
    node = list(federated_ursulas)[0]
    os.environ["TEST_VEHICLE_DATA_EXCHANGE_SEEDNODE_PORT"] = str(node.rest_information()[0].port)

    # import app
    dash_app = import_app('examples.vehicle_data_exchange.vehicle_data_exchange', application_name='app')
    yield dash_app

    # cleanup
    del dash_app
    from examples.vehicle_data_exchange.app import cleanup
    cleanup()
    del os.environ["TEST_VEHICLE_DATA_EXCHANGE_SEEDNODE_PORT"]


@pytest.fixture(scope='function')
def dash_driver(dash_threaded, dash_app):
    dash_threaded(dash_app, start_timeout=30)
    dash_driver = dash_threaded.driver
    home_page = dash_driver.current_window_handle

    yield dash_driver  # provide the fixture value

    # close all windows except for home page
    open_handles = dash_driver.window_handles
    for handle in open_handles:
        if handle != home_page:
            dash_driver.switch_to.window(handle)
            dash_driver.close()

    dash_driver.switch_to.window(home_page)


class wait_for_non_empty_text(object):
    def __init__(self, locator):
        self.locator = locator

    def __call__(self, driver):
        element = driver.find_element(*self.locator)
        if element.text != '':
            return element
        else:
            return False


class wait_until_value_in_text(object):
    def __init__(self, locator, value):
        self.locator = locator
        self.value = value

    def __call__(self, driver):
        element = driver.find_element(*self.locator)
        if self.value in element.text:
            return element
        else:
            return False


def test_alicia_get_policy_key_from_label(dash_driver):
    ######################
    # switch to alicia tab
    ######################
    # open alicia tab
    alicia_link = dash_driver.find_element_by_link_text('ALICIA')
    alicia_link.click()
    dash_driver.switch_to.window('_alicia')

    # derive label and policy key
    create_policy_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                     '#create-policy-button',
                                                                     WAIT_TIMEOUT_SECS)
    create_policy_button.click()

    # wait for response
    policy_key_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'policy-enc-key'))
    )
    policy_label_element = dash_driver.find_element_by_id('policy-label')

    assert 'vehicle-data' in policy_label_element.text
    assert UmbralPublicKey.from_bytes(bytes.fromhex(policy_key_element.text))


def test_alicia_grant(dash_driver):
    ######################
    # switch to alicia tab
    ######################
    # open alicia tab
    alicia_link = dash_driver.find_element_by_link_text('ALICIA')
    alicia_link.click()
    dash_driver.switch_to.window('_alicia')

    # derive label and policy key
    create_policy_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                     '#create-policy-button',
                                                                     WAIT_TIMEOUT_SECS)
    create_policy_button.click()

    # wait for response
    policy_key_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'policy-enc-key'))
    )
    policy_label_element = dash_driver.find_element_by_id('policy-label')

    assert 'vehicle-data' in policy_label_element.text
    assert UmbralPublicKey.from_bytes(bytes.fromhex(policy_key_element.text))

    # grant to some recipient
    m_threshold_element = dash_driver.find_element_by_id('m-value')
    m_threshold_element.send_keys(Keys.ARROW_UP)  # 1 -> 2

    n_shares_element = dash_driver.find_element_by_id('n-value')
    n_shares_element.send_keys(Keys.ARROW_UP)  # 1 -> 2
    n_shares_element.send_keys(Keys.ARROW_UP)  # 2 -> 3

    bob_encrypting_key_hex = UmbralPrivateKey.gen_key().get_pubkey().to_bytes().hex()
    bob_verifying_key_hex = UmbralPrivateKey.gen_key().get_pubkey().to_bytes().hex()

    bob_verifying_key_element = dash_driver.find_element_by_id('recipient-sig-key-grant')
    bob_verifying_key_element.clear()
    bob_verifying_key_element.send_keys(bob_verifying_key_hex)

    bob_encrypting_key_element = dash_driver.find_element_by_id('recipient-enc-key-grant')
    bob_encrypting_key_element.clear()
    bob_encrypting_key_element.send_keys(bob_encrypting_key_hex)

    grant_button = dash_driver.find_element_by_id('grant-button')
    grant_button.click()

    # wait for response
    grant_response_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'grant-response'))
    )

    assert "granted to recipient" in grant_response_element.text
    assert policy_label_element.text in grant_response_element.text
    assert bob_encrypting_key_hex in grant_response_element.text


def test_bob_get_keys(dash_driver):
    ###################
    # switch to bob tab
    ###################
    # open bob tab
    bob_link = dash_driver.find_element_by_link_text('INSURER BOB')
    bob_link.click()
    dash_driver.switch_to.window('_bob')

    # get keys
    get_keys_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                '#get-keys-button',
                                                                WAIT_TIMEOUT_SECS)
    get_keys_button.click()

    # wait for response
    pub_keys_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'pub-keys'))
    )

    keys_text = pub_keys_element.text.split('\n')
    assert len(keys_text) == 4
    assert 'Verifying Key (hex):' == keys_text[0]
    assert UmbralPublicKey.from_bytes(bytes.fromhex(keys_text[1]))
    assert 'Encrypting Key (hex):' == keys_text[2]
    assert UmbralPublicKey.from_bytes(bytes.fromhex(keys_text[3]))


def test_vehicle_data_exchange_ui_lifecycle(dash_driver):
    home_page = dash_driver.current_window_handle

    # open alicia tab
    alicia_link = dash_driver.find_element_by_link_text('ALICIA')
    alicia_link.click()

    dash_driver.switch_to.window(home_page)

    # open enrico tab
    enrico_link = dash_driver.find_element_by_link_text('ENRICO (OBD DEVICE)')
    enrico_link.click()

    dash_driver.switch_to.window(home_page)

    # open bob tab
    bob_link = dash_driver.find_element_by_link_text('INSURER BOB')
    bob_link.click()

    ######################
    # switch to alicia tab
    ######################
    # open alicia tab
    dash_driver.switch_to.window('_alicia')

    # derive label and policy key
    create_policy_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                     '#create-policy-button',
                                                                     WAIT_TIMEOUT_SECS)
    create_policy_button.click()

    # wait for response
    policy_key_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'policy-enc-key'))
    )
    policy_label_element = dash_driver.find_element_by_id('policy-label')
    policy_label = policy_label_element.text

    policy_encrypting_key = policy_key_element.text

    assert 'vehicle-data' in policy_label
    assert UmbralPublicKey.from_bytes(bytes.fromhex(policy_encrypting_key))

    ######################
    # switch to enrico tab
    ######################
    dash_driver.switch_to.window('_enrico')

    start_monitoring_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                        "#generate-button",
                                                                        WAIT_TIMEOUT_SECS)

    policy_encrypting_key_element = dash_driver.find_element_by_id('policy-enc-key')
    policy_encrypting_key_element.clear()
    policy_encrypting_key_element.send_keys(policy_encrypting_key)

    start_monitoring_button.click()

    # wait for response
    last_readings_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'cached-last-readings'))
    )

    assert 'WARNING' not in last_readings_element.text
    # verify that actual number
    assert json.loads(last_readings_element.text)

    ###################
    # switch to bob tab
    ###################
    # open bob tab
    dash_driver.switch_to.window('_bob')

    # get keys
    get_keys_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                '#get-keys-button',
                                                                WAIT_TIMEOUT_SECS)
    get_keys_button.click()

    # wait for response
    pub_keys_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'pub-keys'))
    )

    keys_text = pub_keys_element.text.split('\n')
    assert len(keys_text) == 4

    bob_verifying_key_hex = keys_text[1]
    bob_encrypting_key_hex = keys_text[3]
    assert 'Verifying Key (hex):' == keys_text[0]
    assert UmbralPublicKey.from_bytes(bytes.fromhex(bob_verifying_key_hex))
    assert 'Encrypting Key (hex):' == keys_text[2]
    assert UmbralPublicKey.from_bytes(bytes.fromhex(bob_encrypting_key_hex))

    ######################
    # switch to alicia tab
    ######################
    # open alicia tab
    dash_driver.switch_to.window('_alicia')

    # grant access to bob
    m_threshold_element = dash_driver.find_element_by_id('m-value')
    m_threshold_element.send_keys(Keys.ARROW_UP)  # 1 -> 2

    n_shares_element = dash_driver.find_element_by_id('n-value')
    n_shares_element.send_keys(Keys.ARROW_UP)  # 1 -> 2
    n_shares_element.send_keys(Keys.ARROW_UP)  # 2 -> 3

    bob_verifying_key_element = dash_driver.find_element_by_id('recipient-sig-key-grant')
    bob_verifying_key_element.clear()
    bob_verifying_key_element.send_keys(bob_verifying_key_hex)

    bob_encrypting_key_element = dash_driver.find_element_by_id('recipient-enc-key-grant')
    bob_encrypting_key_element.clear()
    bob_encrypting_key_element.send_keys(bob_encrypting_key_hex)

    grant_button = dash_driver.find_element_by_id('grant-button')
    grant_button.click()

    # wait for response
    grant_response_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'grant-response'))
    )

    assert "granted to recipient" in grant_response_element.text
    assert policy_label in grant_response_element.text
    assert bob_encrypting_key_hex in grant_response_element.text

    ###################
    # switch to bob tab
    ###################
    # open bob tab
    dash_driver.switch_to.window('_bob')

    # read car measurement data
    read_measurements_button = wait_for.wait_for_element_by_css_selector(dash_driver,
                                                                         "#read-button",
                                                                         WAIT_TIMEOUT_SECS)
    read_measurements_button.click()

    # wait for response
    measurements_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'measurements'))
    )
    assert 'WARNING' not in measurements_element.text
    assert 'not been granted' not in measurements_element.text

    ######################
    # switch to alicia tab
    ######################
    # open alicia tab
    dash_driver.switch_to.window('_alicia')

    # revoke access to bob
    revoke_encryption_key_element = dash_driver.find_element_by_id('recipient-enc-key-revoke')
    revoke_encryption_key_element.clear()
    revoke_encryption_key_element.send_keys(bob_encrypting_key_hex)
    revoke_button = dash_driver.find_element_by_id('revoke-button')
    revoke_button.send_keys(Keys.SPACE)  # workaround because element not viewable and can't be directly clicked

    # wait for response
    revoke_response_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_for_non_empty_text((By.ID, 'revoke-response'))
    )

    assert 'WARNING' not in revoke_response_element.text
    assert 'Access revoked to recipient' in revoke_response_element.text
    assert bob_encrypting_key_hex in revoke_response_element.text

    ###################
    # switch to bob tab
    ###################
    # open bob tab
    dash_driver.switch_to.window('_bob')

    revoke_measurements_element = WebDriverWait(dash_driver, WAIT_TIMEOUT_SECS).until(
        wait_until_value_in_text((By.ID, 'measurements'), 'WARNING')
    )
    assert 'WARNING' in revoke_measurements_element.text
    assert 'not been granted' in revoke_measurements_element.text
    assert 'or has been revoked' in revoke_measurements_element.text
