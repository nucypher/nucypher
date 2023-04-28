import pytest

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


@pytest.mark.skip("This test need to be refactored to use some other transaction than deployment")
def test_block_confirmations(testerchain, test_registry, mocker):
    origin = testerchain.etherbase_account
    transacting_power = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    # Mocks and test adjustments
    testerchain.TIMEOUT = 5  # Reduce timeout for tests, for the moment
    mocker.patch.object(testerchain.client, '_calculate_confirmations_timeout', return_value=1)
    EthereumClient.BLOCK_CONFIRMATIONS_POLLING_TIME = 0.1
    EthereumClient.COOLING_TIME = 0

    # Let's try to deploy a simple contract (ReceiveApprovalMethodMock) with 1 confirmation.
    # Since the testerchain doesn't mine new blocks automatically, this fails.
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.deploy_contract(transacting_power=transacting_power,
                                        registry=test_registry,
                                        contract_name='ReceiveApprovalMethodMock',
                                        confirmations=1)

    # Trying again with no confirmation succeeds.
    contract, _ = testerchain.deploy_contract(transacting_power=transacting_power,
                                              registry=test_registry,
                                              contract_name='ReceiveApprovalMethodMock')

    # Trying a simple function of the contract with 1 confirmations fails too, for the same reason
    tx_function = contract.functions.receiveApproval(origin, 0, origin, b'')
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.send_transaction(contract_function=tx_function,
                                         transacting_power=transacting_power,
                                         confirmations=1)

    # Trying again with no confirmation succeeds.
    receipt = testerchain.send_transaction(contract_function=tx_function,
                                           transacting_power=transacting_power,
                                           confirmations=0)
    assert receipt['status'] == 1
