from unittest.mock import PropertyMock

import pytest

from nucypher.blockchain.eth.clients import EthereumClient

CHAIN_ID = 23


@pytest.mark.parametrize("chain_id_return_value", [hex(CHAIN_ID), CHAIN_ID])
def test_cached_chain_id(mocker, chain_id_return_value):
    web3_mock = mocker.MagicMock()
    mock_client = EthereumClient(w3=web3_mock)

    chain_id_property_mock = PropertyMock(return_value=chain_id_return_value)
    type(web3_mock.eth).chain_id = chain_id_property_mock

    assert mock_client.chain_id == CHAIN_ID
    chain_id_property_mock.assert_called_once()

    assert mock_client.chain_id == CHAIN_ID
    chain_id_property_mock.assert_called_once(), "not called again since cached"

    # second instance of client, but uses the same w3 mock
    mock_client_2 = EthereumClient(w3=web3_mock)
    assert mock_client_2.chain_id == CHAIN_ID
    assert (
        chain_id_property_mock.call_count == 2
    ), "additional call since different client instance"

    assert mock_client_2.chain_id == CHAIN_ID
    assert chain_id_property_mock.call_count == 2, "not called again since cached"
