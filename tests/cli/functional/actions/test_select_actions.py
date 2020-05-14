import pytest

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.token import Stake
from nucypher.cli.actions.select import select_stake
from nucypher.cli.literature import ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE


@pytest.fixture()
def mock_stakeholder(test_registry, mock_staking_agent):
    stakeholder = StakeHolder(registry=test_registry)
    return stakeholder


def test_select_stake(test_emitter,
                      mock_staking_agent,
                      test_registry,
                      mock_testerchain,
                      mock_click_prompt,
                      stdout_trap):

    stakes = [(1, 2, 3)]
    mock_staking_agent.get_all_stakes.return_value = stakes
    mock_stakeholder = StakeHolder(registry=test_registry)

    mock_click_prompt.return_value = True
    result = select_stake(emitter=test_emitter, stakeholder=mock_stakeholder)
    assert result

    # Divisible only
    # output = stdout_trap.getvalue()
    # assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE in output
