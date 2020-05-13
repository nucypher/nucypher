from io import StringIO

import click
import pytest

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.confirm import confirm_deployment
from nucypher.cli.literature import ABORT_DEPLOYMENT


@pytest.fixture()
def mock_click_prompt(mocker):
    return mocker.patch.object(click, 'prompt')


@pytest.fixture()
def stdout_trap():
    trap = StringIO()
    return trap


@pytest.fixture()
def test_emitter(mocker, stdout_trap):
    mocker.patch('sys.stdout', new=stdout_trap)
    return StdoutEmitter()


def test_confirm_deployment(mock_click_prompt, test_emitter, stdout_trap, mock_testerchain):

    mock_click_prompt.return_value = False
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    output = stdout_trap.getvalue()
    assert ABORT_DEPLOYMENT in output

    stdout_trap.truncate(0)  # clear

    mock_click_prompt.return_value = 'DEPLOY'  # say the magic word
    result = confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert result

    output = stdout_trap.getvalue()
    assert not output
