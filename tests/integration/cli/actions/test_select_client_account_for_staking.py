"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

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
