import click
from unittest.mock import Mock

import pytest
from eth_utils import is_checksum_address
from web3 import Web3

from nucypher.blockchain.eth.actors import Wallet
from nucypher.blockchain.eth.clients import EthereumClient, EthereumTesterClient
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.token import NU
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.literature import NO_ETH_ACCOUNTS
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import MOCK_PROVIDER_URI, MOCK_SIGNER_URI, NUMBER_OF_ETH_TEST_ACCOUNTS


@pytest.mark.parametrize('selection', range(NUMBER_OF_ETH_TEST_ACCOUNTS))
def test_select_client_account(mock_click_prompt, test_emitter, mock_testerchain, selection):
    """Fine-grained assertions about the return value of interactive client account selection"""
    mock_click_prompt.return_value = selection
    expected_account = mock_testerchain.client.accounts[selection]
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account, "Account selection returned Falsy instead of an address"
    assert isinstance(selected_account, str), "Selection is not a str"
    assert is_checksum_address(selected_account), "Selection is not a valid checksum address"
    assert selected_account == expected_account, "Selection returned the wrong address"


def test_select_client_account_with_no_accounts(mocker,
                                                mock_click_prompt,
                                                test_emitter,
                                                mock_testerchain,
                                                stdout_trap):
    mocker.patch.object(EthereumClient, 'accounts', return_value=[])
    with pytest.raises(click.Abort):
        select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    output = stdout_trap.getvalue()
    assert NO_ETH_ACCOUNTS in output


def test_select_client_account_ambiguous_source(mock_click_prompt, test_emitter, mock_testerchain):

    #
    # Implicit wallet
    #

    error_message = "At least a provider URI or signer URI is necessary to select an account"
    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter)

    error_message = "Pass either signer or signer_uri but not both."
    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter, signer=Mock(), signer_uri=MOCK_SIGNER_URI)

    #
    # Explicit wallet
    #

    error_message = "If pass a wallet, don't pass a signer, provider URI, or signer URI also."
    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter,
                              signer_uri=Mock(),
                              wallet=Mock())

    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter,
                              signer=Mock(),
                              wallet=Mock())

    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter,
                              provider_uri=Mock(),
                              wallet=Mock())


@pytest.mark.parametrize('selection', range(NUMBER_OF_ETH_TEST_ACCOUNTS))
def test_select_client_account_valid_sources(mocker,
                                             mock_click_prompt,
                                             test_emitter,
                                             mock_testerchain,
                                             patch_keystore,
                                             mock_accounts,
                                             selection):

    # Setup
    mock_click_prompt.return_value = selection

    # From External Signer
    selected_account = select_client_account(emitter=test_emitter, signer_uri=MOCK_SIGNER_URI)
    signer_etherbase_keystore = list(mock_accounts.items())[selection]
    _filename, signer_etherbase_account = signer_etherbase_keystore
    expected_account = signer_etherbase_account.address
    assert selected_account == expected_account

    # From Wallet
    expected_account = mock_testerchain.client.accounts[selection]
    wallet = Wallet(provider_uri=MOCK_PROVIDER_URI)
    selected_account = select_client_account(emitter=test_emitter, wallet=wallet)
    assert selected_account == expected_account

    # From pre-initialized Provider
    expected_account = mock_testerchain.client.accounts[selection]
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account == expected_account

    # From uninitialized Provider
    mocker.patch.object(BlockchainInterfaceFactory, 'is_interface_initialized', return_value=False)
    mocker.patch.object(BlockchainInterfaceFactory, '_interfaces', return_value={})
    mocker.patch.object(BlockchainInterfaceFactory, 'get_interface', return_value=mock_testerchain)
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account == expected_account


@pytest.mark.parametrize('selection,show_staking,show_eth,show_tokens,mock_stakes', (
        (0,  True, True, True, []),
        (1, True, True, True, []),
        (5, True, True, True, []),
        (NUMBER_OF_ETH_TEST_ACCOUNTS-1, True, True, True, []),
        (4, True, True, True, [(1, 2, 3)]),
        (7, True, True, True, [(1, 2, 3), (1, 2, 3)]),
        (0, False, True, True, []),
        (0, False, False, True, []),
        (0, False, False, False, []),
))
def test_select_client_account_with_balance_display(mock_click_prompt,
                                                    test_emitter,
                                                    mock_testerchain,
                                                    stdout_trap,
                                                    test_registry_source_manager,
                                                    mock_staking_agent,
                                                    mock_token_agent,
                                                    selection,
                                                    show_staking,
                                                    show_eth,
                                                    show_tokens,
                                                    mock_stakes):

    # Setup
    mock_click_prompt.return_value = selection

    # Missing network kwarg with balance display active
    blockchain_read_required = any((show_staking, show_eth, show_tokens))
    if blockchain_read_required:
        with pytest.raises(ValueError, match='Pass network name or registry; Got neither.'):
            select_client_account(emitter=test_emitter,
                                  show_eth_balance=show_eth,
                                  show_nu_balance=show_tokens,
                                  show_staking=show_staking,
                                  provider_uri=MOCK_PROVIDER_URI)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    selected_account = select_client_account(emitter=test_emitter,
                                             network=TEMPORARY_DOMAIN,
                                             show_eth_balance=show_eth,
                                             show_nu_balance=show_tokens,
                                             show_staking=show_staking,
                                             provider_uri=MOCK_PROVIDER_URI)

    # check for accurate selection consistency with client index
    assert selected_account == mock_testerchain.client.accounts[selection]

    # Display account info
    headers = ['Account']
    if show_staking:
        headers.append('Staking')
    if show_eth:
        headers.append('ETH')
    if show_tokens:
        headers.append('NU')

    raw_output = stdout_trap.getvalue()
    for column_name in headers:
        assert column_name in raw_output, f'"{column_name}" column was not displayed'

    output = raw_output.strip().split('\n')
    body = output[2:-1]
    assert len(body) == len(mock_testerchain.client.accounts), "Some accounts are not displayed"

    accounts = dict()
    for row in body:
        account_display = row.split()
        account_data = dict(zip(headers, account_display[1::]))
        account = account_data['Account']
        accounts[account] = account_data
        assert is_checksum_address(account)

        if show_tokens:
            balance = mock_token_agent.get_balance(address=account)
            assert str(NU.from_nunits(balance)) in row

        if show_eth:
            balance = mock_testerchain.client.get_balance(account=account)
            assert str(Web3.fromWei(balance, 'ether')) in row

        if show_staking:
            if len(mock_stakes) == 0:
                assert "No" in row
            else:
                assert 'Yes' in row
