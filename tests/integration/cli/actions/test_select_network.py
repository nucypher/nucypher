

import pytest

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.actions.select import select_network


__POLY_NETWORKS = NetworksInventory.POLY_NETWORKS
__ETH_NETWORKS = NetworksInventory.ETH_NETWORKS


@pytest.mark.parametrize('user_input', range(0, len(__ETH_NETWORKS)-1))
def test_select_network_cli_action_eth(test_emitter, capsys, mock_stdin, user_input):
    mock_stdin.line(str(user_input))
    selection = __ETH_NETWORKS[user_input]
    result = select_network(emitter=test_emitter, network_type=NetworksInventory.ETH)
    assert result == selection
    assert result not in __POLY_NETWORKS
    captured = capsys.readouterr()
    for name in __ETH_NETWORKS:
        assert name in captured.out
    assert mock_stdin.empty()


def test_select_network_cli_action_neither(test_emitter):
    with pytest.raises(Exception):
        select_network(emitter=test_emitter, network_type="FAKE COIN")
