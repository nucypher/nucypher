import pytest

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.actions.select import select_network

__NETWORKS = NetworksInventory.SUPPORTED_NETWORK_NAMES


@pytest.mark.parametrize("user_input", range(0, len(__NETWORKS) - 1))
def test_select_network_cli_action(test_emitter, capsys, mock_stdin, user_input: int):
    mock_stdin.line(str(user_input))
    selection = __NETWORKS[user_input]
    result = select_network(emitter=test_emitter)
    assert result == selection
    captured = capsys.readouterr()
    for name in __NETWORKS:
        assert name in captured.out
    assert mock_stdin.empty()
