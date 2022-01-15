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


import pytest
from eth_account._utils.legacy_transactions import Transaction
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.crypto.utils import verify_eip_191
from nucypher.crypto.powers import TransactingPower
from tests.conftest import LOCK_FUNCTION
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

TransactingPower.lock_account = LOCK_FUNCTION


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

    transaction_dict = {'nonce': testerchain.client.w3.eth.getTransactionCount(eth_address),
                        'gasPrice': testerchain.client.w3.eth.gasPrice,
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



def test_transacting_power_sign_agent_transaction(testerchain, agency, test_registry):

    token_agent = NucypherTokenAgent(registry=test_registry)
    contract_function = token_agent.contract.functions.approve(testerchain.etherbase_account, 100)

    payload = {'chainId': int(testerchain.client.chain_id),
               'nonce': testerchain.client.w3.eth.getTransactionCount(testerchain.etherbase_account),
               'from': testerchain.etherbase_account,
               'gasPrice': testerchain.client.gas_price}

    unsigned_transaction = contract_function.buildTransaction(payload)

    # Sign with Transacting Power
    transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                         signer=Web3Signer(testerchain.client),
                                         account=testerchain.etherbase_account)
    signed_raw_transaction = transacting_power.sign_transaction(unsigned_transaction)

    # Demonstrate that the transaction is valid RLP encoded.
    restored_transaction = Transaction.from_bytes(serialized_bytes=signed_raw_transaction)
    restored_dict = restored_transaction.as_dict()
    assert to_checksum_address(restored_dict['to']) == unsigned_transaction['to']
