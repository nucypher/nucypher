from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.cli.actions.select import select_client_account_for_staking
from nucypher.cli.literature import PREALLOCATION_STAKE_ADVISORY
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import YES


def test_select_client_account_for_staking_cli_action(test_emitter,
                                                      test_registry,
                                                      test_registry_source_manager,
                                                      mock_click_prompt,
                                                      mock_click_confirm,
                                                      mock_testerchain,
                                                      stdout_trap,
                                                      mocker):
    """Fine-grained assertions about the return value of interactive client account selection"""
    force = False

    selected_index = 0
    selected_account = mock_testerchain.client.accounts[selected_index]

    stakeholder = StakeHolder(registry=test_registry, domains={TEMPORARY_DOMAIN})

    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder,
                                                                        staking_address=selected_account,
                                                                        individual_allocation=None,
                                                                        force=force)
    assert client_account == staking_address == selected_account

    mock_click_prompt.return_value = selected_index
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder,
                                                                        staking_address=None,
                                                                        individual_allocation=None,
                                                                        force=force)
    assert client_account == staking_address == selected_account

    staking_contract_address = '0xFABADA'
    mock_individual_allocation = mocker.Mock(beneficiary_address=selected_account,
                                             contract_address=staking_contract_address)
    mock_click_confirm.return_value = YES
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder,
                                                                        individual_allocation=mock_individual_allocation,
                                                                        staking_address=None,
                                                                        force=force)

    assert client_account == selected_account
    assert staking_address == staking_contract_address

    output = stdout_trap.getvalue()
    message = PREALLOCATION_STAKE_ADVISORY.format(client_account=selected_account,
                                                  staking_address=staking_contract_address)
    assert message in output
