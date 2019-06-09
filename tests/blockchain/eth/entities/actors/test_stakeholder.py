import json
import os

from nucypher.blockchain.eth.actors import StakeHolder


def test_software_stakeholder(testerchain, agency, blockchain_ursulas):

    path = os.path.join('/', 'tmp', 'nucypher-test-stakeholder.json')

    if os.path.exists(path):
        os.remove(path)

    # Create stakeholder from on-chain values given accounts over a web3 provider
    stakeholder = StakeHolder(blockchain=testerchain, trezor=False)

    assert stakeholder.trezor is False
    assert len(stakeholder.stakes)
    assert len(stakeholder.accounts)

    # Save to file
    try:

        # Save the stakeholder JSN config
        stakeholder.to_configuration_file(filepath=path)
        with open(path, 'r') as file:

            # Ensure file contents are serializable
            contents = file.read()
            deserialized_contents = json.loads(contents)

        del stakeholder

        # Restore StakeHolder instance from JSON config
        stakeholder = StakeHolder.from_configuration_file(filepath=path)

        # Save the JSON config again
        stakeholder.to_configuration_file(filepath=path, override=True)
        with open(path, 'r') as file:
            contents = file.read()
            deserialized_contents_2 = json.loads(contents)

        # Ensure the stakeholder was accurately restored from JSON config
        assert deserialized_contents == deserialized_contents_2

    finally:
        if os.path.exists(path):
            os.remove(path)
