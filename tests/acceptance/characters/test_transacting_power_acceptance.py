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

from eth_account._utils.transactions import Transaction
from eth_utils import to_checksum_address

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Character
from nucypher.crypto.utils import verify_eip_191
from nucypher.crypto.powers import (TransactingPower)
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_PROVIDER_URI


def test_character_transacting_power_signing(testerchain, agency, test_registry):

    # Pretend to be a character.
    eth_address = testerchain.etherbase_account
    signer = Character(is_me=True,
                       provider_uri=MOCK_PROVIDER_URI,
                       registry=test_registry,
                       checksum_address=eth_address)

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
    transaction_dict = {'nonce': testerchain.client.w3.eth.getTransactionCount(eth_address),
                        'gasPrice': testerchain.client.w3.eth.gasPrice,
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
