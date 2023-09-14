import pytest

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import Logger
from tests.utils.ursula import select_test_port

logger = Logger("test-operator")

def log(message):
    logger.debug(message)
    print(message)


@pytest.mark.usefixtures("test_registry_source_manager")
def test_ursula_operator_confirmation(
    ursula_test_config,
    testerchain,
    threshold_staking,
    taco_application_agent,
    test_registry,
    deployer_account,
):
    staking_provider = testerchain.stake_provider_account(0)
    operator_address = testerchain.ursula_account(0)
    min_authorization = taco_application_agent.get_min_authorization()

    # make an staking_providers and some stakes
    threshold_staking.setRoles(staking_provider, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider,
        0,
        min_authorization,
        sender=deployer_account,
    )

    # not staking provider just yet
    assert (
        taco_application_agent.get_staking_provider_from_operator(operator_address)
        == NULL_ADDRESS
    )
    assert taco_application_agent.is_operator_confirmed(operator_address) is False

    # bond this operator
    tpower = TransactingPower(
        account=staking_provider, signer=Web3Signer(testerchain.client)
    )
    taco_application_agent.bond_operator(
        staking_provider=staking_provider,
        operator=operator_address,
        transacting_power=tpower,
    )

    # make an ursula.
    ursula = ursula_test_config.produce(
        operator_address=operator_address, rest_port=select_test_port()
    )

    # now the worker has a staking provider
    assert ursula.get_staking_provider_address() == staking_provider
    # confirmed on Ursula creation
    assert ursula.is_confirmed is True
