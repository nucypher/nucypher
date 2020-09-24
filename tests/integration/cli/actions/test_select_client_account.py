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

import click
import pytest
from eth_utils import is_checksum_address
from unittest.mock import Mock
from web3 import Web3

from nucypher.blockchain.eth.actors import Wallet
from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.token import NU
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.literature import (
    NO_ETH_ACCOUNTS,
    GENERIC_SELECT_ACCOUNT,
    )
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.types import SubStakeInfo
from tests.constants import MOCK_PROVIDER_URI, MOCK_SIGNER_URI, NUMBER_OF_ETH_TEST_ACCOUNTS


@pytest.mark.parametrize('selection', range(NUMBER_OF_ETH_TEST_ACCOUNTS))
def test_select_client_account(mock_stdin, test_emitter, mock_testerchain, selection, capsys):
    """Fine-grained assertions about the return value of interactive client account selection"""
    mock_stdin.line(str(selection))
    expected_account = mock_testerchain.client.accounts[selection]
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account, "Account selection returned Falsy instead of an address"
    assert isinstance(selected_account, str), "Selection is not a str"
    assert is_checksum_address(selected_account), "Selection is not a valid checksum address"
    assert selected_account == expected_account, "Selection returned the wrong address"
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out


def test_select_client_account_with_no_accounts(mocker,
                                                mock_stdin, # used to assert the user was not prompted
                                                test_emitter,
                                                mock_testerchain,
                                                capsys):
    mocker.patch.object(EthereumClient, 'accounts', return_value=[])
    with pytest.raises(click.Abort):
        select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    captured = capsys.readouterr()
    assert NO_ETH_ACCOUNTS in captured.out


def test_select_client_account_ambiguous_source(mock_stdin, # used to assert the user was not prompted
                                                test_emitter,
                                                mock_testerchain):

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

    error_message = "If a wallet is provided, don't provide a signer, provider URI, or signer URI."
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
                                             mock_stdin,
                                             test_emitter,
                                             mock_testerchain,
                                             patch_keystore,
                                             mock_accounts,
                                             selection,
                                             capsys):

    # From External Signer
    mock_stdin.line(str(selection))
    mock_signer = mocker.patch.object(KeystoreSigner, 'from_signer_uri')
    selected_account = select_client_account(emitter=test_emitter, signer_uri=MOCK_SIGNER_URI)
    expected_account = mock_testerchain.client.accounts[selection]
    assert selected_account == expected_account
    mock_signer.assert_called_once_with(uri=MOCK_SIGNER_URI, testnet=True)
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From Wallet
    mock_stdin.line(str(selection))
    expected_account = mock_testerchain.client.accounts[selection]
    wallet = Wallet(provider_uri=MOCK_PROVIDER_URI)
    selected_account = select_client_account(emitter=test_emitter, wallet=wallet)
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From pre-initialized Provider
    mock_stdin.line(str(selection))
    expected_account = mock_testerchain.client.accounts[selection]
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From uninitialized Provider
    mock_stdin.line(str(selection))
    mocker.patch.object(BlockchainInterfaceFactory, 'is_interface_initialized', return_value=False)
    mocker.patch.object(BlockchainInterfaceFactory, '_interfaces', return_value={})
    mocker.patch.object(BlockchainInterfaceFactory, 'get_interface', return_value=mock_testerchain)
    selected_account = select_client_account(emitter=test_emitter, provider_uri=MOCK_PROVIDER_URI)
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out


@pytest.mark.parametrize('selection,show_staking,show_eth,show_tokens,stake_info', (
        (0,  True, True, True, []),
        (1, True, True, True, []),
        (5, True, True, True, []),
        (NUMBER_OF_ETH_TEST_ACCOUNTS-1, True, True, True, []),
        (4, True, True, True, [SubStakeInfo(1, 2, 3)]),
        (7, True, True, True, [SubStakeInfo(1, 2, 3), SubStakeInfo(1, 2, 3)]),
        (0, False, True, True, []),
        (0, False, False, True, []),
        (0, False, False, False, []),
))
def test_select_client_account_with_balance_display(mock_stdin,
                                                    test_emitter,
                                                    mock_testerchain,
                                                    capsys,
                                                    test_registry_source_manager,
                                                    mock_staking_agent,
                                                    mock_token_agent,
                                                    selection,
                                                    show_staking,
                                                    show_eth,
                                                    show_tokens,
                                                    stake_info):

    # Setup
    mock_staking_agent.get_all_stakes.return_value = stake_info

    # Missing network kwarg with balance display active
    blockchain_read_required = any((show_staking, show_eth, show_tokens))
    if blockchain_read_required:
        with pytest.raises(ValueError, match='Pass network name or registry; Got neither.'):
            select_client_account(emitter=test_emitter,
                                  show_eth_balance=show_eth,
                                  show_nu_balance=show_tokens,
                                  show_staking=show_staking,
                                  provider_uri=MOCK_PROVIDER_URI)

    # Good selection
    mock_stdin.line(str(selection))
    selected_account = select_client_account(emitter=test_emitter,
                                             network=TEMPORARY_DOMAIN,
                                             show_eth_balance=show_eth,
                                             show_nu_balance=show_tokens,
                                             show_staking=show_staking,
                                             provider_uri=MOCK_PROVIDER_URI)

    # check for accurate selection consistency with client index
    assert selected_account == mock_testerchain.client.accounts[selection]
    assert mock_stdin.empty()

    # Display account info
    headers = ['Account']
    if show_staking:
        headers.append('Staking')
    if show_eth:
        headers.append('ETH')
    if show_tokens:
        headers.append('NU')

    captured = capsys.readouterr()
    for column_name in headers:
        assert column_name in captured.out, f'"{column_name}" column was not displayed'

    for account in mock_testerchain.client.accounts:
        assert account in captured.out

        if show_tokens:
            balance = mock_token_agent.get_balance(address=account)
            assert str(NU.from_nunits(balance)) in captured.out

        if show_eth:
            balance = mock_testerchain.client.get_balance(account=account)
            assert str(Web3.fromWei(balance, 'ether')) in captured.out

        if show_staking:
            if len(stake_info) == 0:
                assert "No" in captured.out
            else:
                assert 'Yes' in captured.out
