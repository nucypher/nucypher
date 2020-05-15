import pytest

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.actions.select import select_network


@pytest.mark.parametrize('user_input', range(len(NetworksInventory.NETWORKS)))
def test_select_network(test_emitter, stdout_trap, mock_click_prompt, user_input):
    mock_click_prompt.return_value = user_input
    networks = NetworksInventory.NETWORKS
    selection = networks[user_input]
    result = select_network(emitter=test_emitter)
    assert result == selection
    output = stdout_trap.getvalue()
    for name in networks:
        assert name in output
