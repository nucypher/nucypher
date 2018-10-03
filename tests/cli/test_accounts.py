import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.mark.usefixtures("three_agents")
def test_list(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[0]
    args = '--dev --provider-uri tester://pyevm accounts list'.split()
    result = runner.invoke(cli, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert account in result.output


@pytest.mark.usefixtures("three_agents")
def test_balance(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[0]
    args = '--dev --provider-uri tester://pyevm accounts balance'.split()
    result = runner.invoke(cli, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'Tokens:' in result.output
    assert 'ETH:' in result.output
    assert account in result.output


@pytest.mark.usefixtures("three_agents")
def test_transfer_eth(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[1]
    args = '--dev --provider-uri tester://pyevm accounts transfer-eth'.split()
    result = runner.invoke(cli, args, catch_exceptions=False, input=account+'\n100\nY\n')
    assert result.exit_code == 0


@pytest.mark.usefixtures("three_agents")
def test_transfer_tokens(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[2]
    args = '--provider-uri tester://pyevm accounts transfer-tokens'.split()
    result = runner.invoke(cli, args, catch_exceptions=False, input=account+'\n100\nY\n')
    assert result.exit_code == 0
