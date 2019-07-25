import pytest
from eth_account._utils.transactions import Transaction
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.crypto.api import verify_eip_191
from nucypher.crypto.powers import (PowerUpError)
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_transacting_power_sign_message(testerchain):

    # Manually create a TransactingPower
    testerchain.connect()
    eth_address = testerchain.etherbase_account
    power = TransactingPower(blockchain=testerchain,
                             password=INSECURE_DEVELOPMENT_PASSWORD,
                             account=eth_address)

    # The default state of the account is locked.
    # Test a signature without unlocking the account
    with pytest.raises(PowerUpError):
        power.sign_message(message=b'test')

    # Manually unlock
    power.unlock_account(password=INSECURE_DEVELOPMENT_PASSWORD)

    # Sign
    data_to_sign = b'Premium Select Luxury Pencil Holder'
    signature = power.sign_message(message=data_to_sign)

    # Verify
    is_verified = verify_eip_191(address=eth_address, message=data_to_sign, signature=signature)
    assert is_verified is True

    # Test invalid address/pubkey pair
    is_verified = verify_eip_191(address=testerchain.client.accounts[1],
                                 message=data_to_sign,
                                 signature=signature)
    assert is_verified is False

    # Test lockAccount call
    power.lock_account()

    # Test a signature without unlocking the account
    with pytest.raises(PowerUpError):
        power.sign_message(message=b'test')

    del power      # Locks account


def test_transacting_power_sign_transaction(testerchain):

    eth_address = testerchain.unassigned_accounts[2]
    power = TransactingPower(blockchain=testerchain,
                             password=INSECURE_DEVELOPMENT_PASSWORD,
                             account=eth_address)

    assert power.is_active is False
    assert power.is_unlocked is False

    transaction_dict = {'nonce': testerchain.client.w3.eth.getTransactionCount(eth_address),
                        'gasPrice': testerchain.client.w3.eth.gasPrice,
                        'gas': 100000,
                        'from': eth_address,
                        'to': testerchain.unassigned_accounts[1],
                        'value': 1,
                        'data': b''}

    # The default state of the account is locked.
    # Test a signature without unlocking the account
    with pytest.raises(TransactingPower.AccountLocked):
        power.sign_transaction(unsigned_transaction=transaction_dict)

    # Sign
    power.activate()
    assert power.is_unlocked is True
    signed_transaction = power.sign_transaction(unsigned_transaction=transaction_dict)

    # Demonstrate that the transaction is valid RLP encoded.
    from eth_account._utils.transactions import Transaction
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == transaction_dict['to']

    # Try signing with missing transaction fields
    del transaction_dict['gas']
    del transaction_dict['nonce']
    with pytest.raises(TypeError):
        power.sign_transaction(unsigned_transaction=transaction_dict)

    # Try signing with a re-locked account.
    power.lock_account()
    with pytest.raises(TransactingPower.AccountLocked):
        power.sign_transaction(unsigned_transaction=transaction_dict)

    power.unlock_account(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert power.is_unlocked is True

    # Tear-Down Test
    power = TransactingPower(blockchain=testerchain,
                             password=INSECURE_DEVELOPMENT_PASSWORD,
                             account=testerchain.etherbase_account)
    power.activate(password=INSECURE_DEVELOPMENT_PASSWORD)


def test_transacting_power_sign_agent_transaction(testerchain, agency):

    token_agent = NucypherTokenAgent(blockchain=testerchain)
    contract_function = token_agent.contract.functions.approve(testerchain.etherbase_account, 100)

    payload = {'chainId': int(testerchain.client.net_version),
               'nonce': testerchain.client.w3.eth.getTransactionCount(testerchain.etherbase_account),
               'from': testerchain.etherbase_account,
               'gasPrice': testerchain.client.gas_price}

    unsigned_transaction = contract_function.buildTransaction(payload)

    # Sign with Transacting Power
    transacting_power = TransactingPower(blockchain=testerchain,
                                         password=INSECURE_DEVELOPMENT_PASSWORD,
                                         account=testerchain.etherbase_account)
    transacting_power.activate()
    signed_raw_transaction = transacting_power.sign_transaction(unsigned_transaction)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_raw_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == unsigned_transaction['to']
