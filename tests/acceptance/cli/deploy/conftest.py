

import pytest

from nucypher.blockchain.eth.clients import EthereumClient


@pytest.fixture(scope='function', autouse=True)
def monkeypatch_confirmations(testerchain, monkeypatch):
    def block_until_enough_confirmations(ethclient: EthereumClient, transaction_hash, *args, **kwargs):
        ethclient.log.debug(f'Confirmations mocked - instantly confirmed {kwargs.get("confirmations")} blocks!')
        return testerchain.wait_for_receipt(txhash=transaction_hash)
    monkeypatch.setattr(EthereumClient, 'block_until_enough_confirmations', block_until_enough_confirmations)
