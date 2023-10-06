import pytest
from eth_account._utils.legacy_transactions import Transaction
from eth_utils import to_checksum_address
from nucypher_core.ferveo import Keypair

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Character
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.utils import verify_eip_191
from tests.conftest import LOCK_FUNCTION
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, TEST_ETH_PROVIDER_URI

TransactingPower.lock_account = LOCK_FUNCTION


def test_character_transacting_power_signing(testerchain, test_registry):

    # Pretend to be a character.
    eth_address = testerchain.etherbase_account
    signer = Character(
        is_me=True,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=TEST_ETH_PROVIDER_URI,
        registry=test_registry,
        checksum_address=eth_address,
    )

    # Manually consume the power up
    transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                         signer=Web3Signer(testerchain.client),
                                         account=eth_address)

    signer._crypto_power.consume_power_up(transacting_power)

    # Retrieve the power up
    power = signer._crypto_power.power_ups(TransactingPower)

    assert power == transacting_power

    # Sign Message
    data_to_sign = b'Premium Select Luxury Pencil Holder'
    signature = power.sign_message(message=data_to_sign)
    is_verified = verify_eip_191(address=eth_address, message=data_to_sign, signature=signature)
    assert is_verified is True

    # Sign Transaction
    transaction_dict = {'nonce': testerchain.client.w3.eth.get_transaction_count(eth_address),
                        'gasPrice': testerchain.client.w3.eth.gas_price,
                        'gas': 100000,
                        'from': eth_address,
                        'to': testerchain.unassigned_accounts[1],
                        'value': 1,
                        'data': b''}

    signed_transaction = power.sign_transaction(transaction_dict=transaction_dict)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == transaction_dict['to']


def test_transacting_power_sign_message(testerchain):

    # Manually create a TransactingPower
    eth_address = testerchain.etherbase_account
    power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                             signer=Web3Signer(testerchain.client),
                             account=eth_address)

    # Manually unlock
    power.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

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


def test_transacting_power_sign_transaction(testerchain):

    eth_address = testerchain.unassigned_accounts[2]
    power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                             signer=Web3Signer(testerchain.client),
                             account=eth_address)

    transaction_dict = {'nonce': testerchain.client.w3.eth.get_transaction_count(eth_address),
                        'gasPrice': testerchain.client.w3.eth.gas_price,
                        'gas': 100000,
                        'from': eth_address,
                        'to': testerchain.unassigned_accounts[1],
                        'value': 1,
                        'data': b''}

    # Sign
    power.activate()
    signed_transaction = power.sign_transaction(transaction_dict=transaction_dict)

    # Demonstrate that the transaction is valid RLP encoded.
    from eth_account._utils.legacy_transactions import Transaction
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == transaction_dict['to']

    # Try signing with missing transaction fields
    del transaction_dict['gas']
    del transaction_dict['nonce']
    with pytest.raises(TypeError):
        power.sign_transaction(transaction_dict=transaction_dict)


def test_transacting_power_sign_agent_transaction(testerchain, coordinator_agent):
    public_key = Keypair.random().public_key()
    g2_point = coordinator_agent.G2Point.from_public_key(public_key)
    contract_function = coordinator_agent.contract.functions.setProviderPublicKey(
        g2_point
    )

    payload = {'chainId': int(testerchain.client.chain_id),
               'nonce': testerchain.client.w3.eth.get_transaction_count(testerchain.etherbase_account),
               'from': testerchain.etherbase_account,
               'gasPrice': testerchain.client.gas_price,
               'gas': 500_000}

    unsigned_transaction = contract_function.build_transaction(payload)

    # Sign with Transacting Power
    transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                         signer=Web3Signer(testerchain.client),
                                         account=testerchain.etherbase_account)
    signed_raw_transaction = transacting_power.sign_transaction(unsigned_transaction)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_raw_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == unsigned_transaction['to']
