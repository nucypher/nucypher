import pytest

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.actions.select import select_network


__NETWORKS = NetworksInventory.NETWORKS


@pytest.mark.parametrize('user_input', range(0, len(__NETWORKS)-1))
def test_select_network_cli_action(test_emitter, stdout_trap, mock_click_prompt, user_input):
    mock_click_prompt.return_value = user_input
    selection = __NETWORKS[user_input]
    result = select_network(emitter=test_emitter)
    assert result == selection
    output = stdout_trap.getvalue()
    for name in __NETWORKS:
        assert name in output
