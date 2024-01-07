import pytest
from eth_account._utils.legacy_transactions import Transaction
from eth_utils import to_checksum_address
from nucypher_core.ferveo import Keypair

from nucypher.blockchain.eth.wallets import Wallet
from nucypher.crypto.utils import verify_eip_191


def test_sign_message_text(accounts, test_registry, testerchain):
    wallet = accounts.etherbase_wallet
    data_to_sign = b'Premium Select Luxury Pencil Holder'
    signature = wallet.sign_message(message=data_to_sign)
    is_verified = verify_eip_191(address=wallet.address, message=data_to_sign, signature=signature)
    assert is_verified is True


def test_sign_transaction(accounts, test_registry, testerchain):
    wallet = accounts.etherbase_wallet

    transaction_dict = {'nonce': testerchain.client.w3.eth.get_transaction_count(wallet.address),
                        'gasPrice': testerchain.client.w3.eth.gas_price,
                        'gas': 100000,
                        'from': wallet.address,
                        'to': accounts.unassigned_wallets[1].address,
                        'value': 1,
                        'data': b''}

    signed_transaction = wallet.sign_transaction(transaction_dict=transaction_dict)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == transaction_dict['to']


def test_wallet_sign_message():
    wallet = Wallet.random()

    # Sign
    data_to_sign = b'Premium Select Luxury Pencil Holder'
    signature = wallet.sign_message(message=data_to_sign)

    # Verify
    is_verified = verify_eip_191(address=wallet.address, message=data_to_sign, signature=signature)
    assert is_verified is True

    # Test invalid address/pubkey pair
    is_verified = verify_eip_191(address=Wallet.random().address,
                                 message=data_to_sign,
                                 signature=signature)
    assert is_verified is False


def test_wallet_sign_transaction(testerchain, accounts):
    wallet = Wallet.random()

    transaction_dict = {'nonce': testerchain.client.w3.eth.get_transaction_count(wallet.address),
                        'gasPrice': testerchain.client.w3.eth.gas_price,
                        'gas': 100000,
                        'from': wallet.address,
                        'to': accounts.unassigned_wallets[1].address,
                        'value': 1,
                        'data': b''}

    # Sign
    signed_transaction = wallet.sign_transaction(transaction_dict=transaction_dict)

    # Demonstrate that the transaction is valid RLP encoded.
    from eth_account._utils.legacy_transactions import Transaction
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == transaction_dict['to']

    # Try signing with missing transaction fields
    del transaction_dict['gas']
    del transaction_dict['nonce']
    with pytest.raises(TypeError):
        wallet.sign_transaction(transaction_dict=transaction_dict)


def test_wallet_sign_agent_transaction(testerchain, accounts, coordinator_agent):
    wallet = Wallet.random()

    public_key = Keypair.random().public_key()
    g2_point = coordinator_agent.G2Point.from_public_key(public_key)
    contract_function = coordinator_agent.contract.functions.setProviderPublicKey(
        g2_point
    )

    payload = {'chainId': int(testerchain.client.chain_id),
               'nonce': testerchain.client.w3.eth.get_transaction_count(wallet.address),
               'from': wallet.address,
               'gasPrice': testerchain.client.gas_price,
               'gas': 500_000}

    unsigned_transaction = contract_function.build_transaction(payload)

    signed_raw_transaction = wallet.sign_transaction(unsigned_transaction)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_raw_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == unsigned_transaction['to']
