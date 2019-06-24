import json
import os

import pytest

from nucypher.blockchain.eth.actors import StakeHolder


@pytest.fixture(scope='session')
def stakeholder_config_file_location():
    path = os.path.join('/', 'tmp', 'nucypher-test-stakeholder.json')
    return path


@pytest.fixture(scope='module')
def staking_software_stakeholder(testerchain,
                                 agency,
                                 blockchain_ursulas,
                                 stakeholder_config_file_location):

    # Setup
    path = stakeholder_config_file_location
    if os.path.exists(path):
        os.remove(path)

    # Create stakeholder from on-chain values given accounts over a web3 provider
    stakeholder = StakeHolder(blockchain=testerchain, trezor=False)

    # Teardown
    yield stakeholder
    if os.path.exists(path):
        os.remove(path)


def test_software_stakeholder_configuration(testerchain,
                                            staking_software_stakeholder,
                                            stakeholder_config_file_location):

    stakeholder = staking_software_stakeholder
    path = stakeholder_config_file_location

    # Check attributes can be successfully read
    assert stakeholder.total_stake
    assert stakeholder.trezor is False
    assert stakeholder.stakes
    assert stakeholder.accounts

    # Save the stakeholder JSON config
    stakeholder.to_configuration_file(filepath=path)
    with open(stakeholder.filepath, 'r') as file:

        # Ensure file contents are serializable
        contents = file.read()
        first_config_contents = json.loads(contents)

    # Destroy this stake holder, leaving only the configuration file behind
    del stakeholder

    # Restore StakeHolder instance from JSON config
    the_same_stakeholder = StakeHolder.from_configuration_file(filepath=path, blockchain=testerchain)

    # Save the JSON config again
    the_same_stakeholder.to_configuration_file(filepath=path, override=True)
    with open(the_same_stakeholder.filepath, 'r') as file:
        contents = file.read()
        second_config_contents = json.loads(contents)

    # Ensure the stakeholder was accurately restored from JSON config
    assert first_config_contents == second_config_contents
