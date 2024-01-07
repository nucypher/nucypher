from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.utilities.logging import Logger
from tests.utils.ursula import select_test_port

logger = Logger("test-operator")


def log(message):
    logger.debug(message)
    print(message)


def test_ursula_operator_confirmation(
    ursula_test_config,
    accounts,
    threshold_staking,
    taco_application_agent,
    taco_child_application_agent,
    test_registry,
    deployer_account,
):
    staking_provider_wallet = accounts.provider_wallet(0)
    operator_wallet = accounts.ursula_wallet(0)
    operator_address = operator_wallet.address
    min_authorization = taco_application_agent.get_min_authorization()

    # make an staking_providers and some stakes
    threshold_staking.setRoles(staking_provider_wallet.address, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider_wallet.address,
        0,
        min_authorization,
        sender=deployer_account,
    )

    # not staking provider just yet
    assert (
        taco_application_agent.get_staking_provider_from_operator(operator_address)
        == NULL_ADDRESS
    )
    assert (
        taco_child_application_agent.staking_provider_from_operator(operator_address)
        == NULL_ADDRESS
    )
    assert taco_application_agent.is_operator_confirmed(operator_address) is False
    assert taco_child_application_agent.is_operator_confirmed(operator_address) is False

    taco_application_agent.bond_operator(
        staking_provider=staking_provider_wallet.address,
        operator=operator_address,
        wallet=staking_provider_wallet,
    )

    # make an ursula.
    ursula = ursula_test_config.produce(
        wallet=operator_wallet,
        rest_port=select_test_port()
    )

    # now the worker has a staking provider
    assert ursula.get_staking_provider_address() == staking_provider_wallet.address

    # confirmed once ursula has set provider public key
    ursula.set_provider_public_key()

    assert ursula.is_confirmed is True

    assert taco_application_agent.is_operator_confirmed(operator_address) is True
    assert taco_child_application_agent.is_operator_confirmed(operator_address) is True
