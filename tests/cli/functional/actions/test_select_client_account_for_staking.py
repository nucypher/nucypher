import pytest

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.cli.actions.select import select_client_account_for_staking
from nucypher.config.constants import TEMPORARY_DOMAIN


@pytest.mark.skip(reason="David, please send help.")
def test_handle_client_account_for_staking(test_emitter, test_registry, test_registry_source_manager):
    stakeholder = StakeHolder(registry=test_registry)
    force = False
    registry = IndividualAllocationRegistry(beneficiary_address='0xdeadbeef',
                                            contract_address='0xdeadbeef',
                                            network=TEMPORARY_DOMAIN)
    result = select_client_account_for_staking(emitter=test_emitter,
                                               stakeholder=stakeholder,
                                               staking_address='0xdeadbeef',
                                               individual_allocation=registry,
                                               force=force)

    assert result
