


from unittest.mock import Mock

import click
import pytest
from eth_utils import is_checksum_address
from web3 import Web3

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.signers import KeystoreSigner
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.cli.actions.select import select_client_account
from nucypher.cli.literature import GENERIC_SELECT_ACCOUNT, NO_ACCOUNTS
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import (
    MOCK_ETH_PROVIDER_URI,
    MOCK_SIGNER_URI,
    NUMBER_OF_ETH_TEST_ACCOUNTS,
)


@pytest.mark.parametrize("selection", range(NUMBER_OF_ETH_TEST_ACCOUNTS))
def test_select_client_account(
    mock_stdin, test_emitter, testerchain, selection, capsys
):
    """Fine-grained assertions about the return value of interactive client account selection"""
    mock_stdin.line(str(selection))
    expected_account = testerchain.client.accounts[selection]
    selected_account = select_client_account(
        emitter=test_emitter,
        signer=Web3Signer(testerchain.client),
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    assert selected_account, "Account selection returned Falsy instead of an address"
    assert isinstance(selected_account, str), "Selection is not a str"
    assert is_checksum_address(selected_account), "Selection is not a valid checksum address"
    assert selected_account == expected_account, "Selection returned the wrong address"
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out


def test_select_client_account_with_no_accounts(
    mocker,
    mock_stdin,  # used to assert the user was not prompted
    test_emitter,
    testerchain,
    capsys,
):
    mocker.patch.object(EthereumClient, "accounts", return_value=[])
    with pytest.raises(click.Abort):
        select_client_account(
            emitter=test_emitter,
            signer=Web3Signer(testerchain.client),
            polygon_endpoint=MOCK_ETH_PROVIDER_URI,
        )
    captured = capsys.readouterr()
    assert NO_ACCOUNTS in captured.out


def test_select_client_account_ambiguous_source(
    mock_stdin, test_emitter, testerchain  # used to assert the user was not prompted
):

    #
    # Implicit wallet  # TODO: Are all cases covered?
    #

    error_message = "At least a provider URI, signer URI or signer must be provided to select an account"
    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter)

    error_message = "Pass either signer or signer_uri but not both."
    with pytest.raises(ValueError, match=error_message):
        select_client_account(emitter=test_emitter, signer=Mock(), signer_uri=MOCK_SIGNER_URI)


@pytest.mark.parametrize("selection", range(NUMBER_OF_ETH_TEST_ACCOUNTS))
def test_select_client_account_valid_sources(
    mocker,
    mock_stdin,
    test_emitter,
    testerchain,
    patch_keystore,
    mock_accounts,
    selection,
    capsys,
):

    # From External Signer
    mock_stdin.line(str(selection))
    mock_signer = mocker.patch.object(
        KeystoreSigner, "from_signer_uri", return_value=Web3Signer(testerchain.client)
    )
    selected_account = select_client_account(
        emitter=test_emitter, signer_uri=MOCK_SIGNER_URI
    )
    expected_account = testerchain.client.accounts[selection]
    assert selected_account == expected_account
    mock_signer.assert_called_once_with(uri=MOCK_SIGNER_URI, testnet=True)
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From Wallet
    mock_stdin.line(str(selection))
    expected_account = testerchain.client.accounts[selection]
    selected_account = select_client_account(
        emitter=test_emitter, signer=Web3Signer(testerchain.client)
    )
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From pre-initialized Provider
    mock_stdin.line(str(selection))
    expected_account = testerchain.client.accounts[selection]
    selected_account = select_client_account(
        emitter=test_emitter, polygon_endpoint=MOCK_ETH_PROVIDER_URI
    )
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out

    # From uninitialized Provider
    mock_stdin.line(str(selection))
    mocker.patch.object(
        BlockchainInterfaceFactory, "is_interface_initialized", return_value=False
    )
    mocker.patch.object(BlockchainInterfaceFactory, "_interfaces", return_value={})
    mocker.patch.object(
        BlockchainInterfaceFactory, "get_interface", return_value=testerchain
    )
    selected_account = select_client_account(
        emitter=test_emitter, polygon_endpoint=MOCK_ETH_PROVIDER_URI
    )
    assert selected_account == expected_account
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert GENERIC_SELECT_ACCOUNT in captured.out and f"Selected {selection}" in captured.out


@pytest.mark.skip("fix me")
@pytest.mark.parametrize(
    "selection,show_staking,show_matic,stake_info",
    (
        (0, True, True, []),
        (1, True, True, []),
        (5, True, True, []),
        (NUMBER_OF_ETH_TEST_ACCOUNTS - 1, True, True, []),
        (0, False, True, []),
        (0, False, False, []),
        (0, False, False, []),
    ),
)
def test_select_client_account_with_balance_display(
    mock_stdin,
    test_emitter,
    testerchain,
    capsys,
    mock_staking_agent,
    mock_token_agent,
    selection,
    show_staking,
    show_matic,
    stake_info,
):

    # Setup
    mock_staking_agent.get_all_stakes.return_value = stake_info

    # Missing network kwarg with balance display active
    blockchain_read_required = any((show_staking, show_matic))
    if blockchain_read_required:
        with pytest.raises(
            ValueError, match="Pass domain name or registry; Got neither."
        ):
            select_client_account(
                emitter=test_emitter,
                show_matic_balance=show_matic,
                show_staking=show_staking,
                polygon_endpoint=MOCK_ETH_PROVIDER_URI,
            )

    # Good selection
    mock_stdin.line(str(selection))
    selected_account = select_client_account(
        emitter=test_emitter,
        domain=TEMPORARY_DOMAIN,
        show_matic_balance=show_matic,
        show_staking=show_staking,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    # check for accurate selection consistency with client index
    assert selected_account == testerchain.client.accounts[selection]
    assert mock_stdin.empty()

    # Display account info
    headers = ['Account']
    if show_staking:
        headers.append('Staking')
    if show_matic:
        headers.append("MATIC")

    captured = capsys.readouterr()
    for column_name in headers:
        assert column_name in captured.out, f'"{column_name}" column was not displayed'

    for account in testerchain.client.accounts:
        assert account in captured.out

        if show_matic:
            balance = testerchain.client.get_balance(account=account)
            assert str(Web3.from_wei(balance, 'ether')) in captured.out

        if show_staking:
            if len(stake_info) == 0:
                assert "No" in captured.out
            else:
                assert 'Yes' in captured.out
