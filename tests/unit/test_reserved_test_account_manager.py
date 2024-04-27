from tests.constants import NUMBER_OF_ETH_TEST_ACCOUNTS
from tests.utils.blockchain import ReservedTestAccountManager


def test_account_organization():
    account_manager = ReservedTestAccountManager()

    account_addresses = account_manager.accounts_addresses
    assert (
        len(set(account_addresses)) == NUMBER_OF_ETH_TEST_ACCOUNTS
    ), "all unique addresses"

    # special accounts
    assert account_manager.etherbase_account == account_addresses[0]
    assert account_manager.alice_account == account_addresses[1]
    assert account_manager.bob_account == account_addresses[2]

    # staking provider addresses
    staking_providers = account_manager.staking_providers_accounts
    assert staking_providers == account_addresses[3:13]
    for i in range(len(staking_providers)):
        assert account_manager.staking_provider_account(i) == staking_providers[i]

    # ursula addresses
    ursulas = account_manager.ursulas_accounts
    assert ursulas == account_addresses[13:23]
    for i in range(len(ursulas)):
        assert account_manager.ursula_account(i) == ursulas[i]

    # unassigned addresses
    assert account_manager.unassigned_accounts == account_addresses[23:30]
