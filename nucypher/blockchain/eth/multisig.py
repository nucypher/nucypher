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

import json
from collections import namedtuple
from typing import List

from eth_abi.packed import encode_single_packed
from web3 import Web3


class Proposal:

    def __init__(self, trustee_address, target_address, value, data, nonce, digest):
        self.trustee_address = trustee_address
        self.target_address = target_address
        self.value = value
        self.data = data
        self.nonce = nonce
        self.digest = digest

    @classmethod
    def from_transaction(cls, transaction, multisig_agent):
        proposal_elements = dict(trustee_address=transaction['from'],
                                 target_address=transaction['to'],
                                 value=transaction['value'],
                                 data=Web3.toBytes(hexstr=transaction['data']),
                                 nonce=multisig_agent.nonce)

        digest = multisig_agent.get_unsigned_transaction_hash(**proposal_elements)
        proposal_elements.update(digest=digest)

        return cls(**proposal_elements)

    @property
    def application_specific_data(self) -> bytes:  # TODO: Think a better name, perhaps something related to "message body" or something like that
        """
        In EIP191 version 0 signatures, data to be signed follows the following format:

            0x19 + 0x00 + validator_address + application_specific_data

        In the context of our MultiSig (which is the "validator"), the application specific data is the concatenation of:
          - Trustee address (actual sender of the TX)
          - Target address
          - Value included in the transaction (in wei)
          - Transaction data (e.g., an encoded call to a contract function)
          - MultiSig nonce
        """

        typed_elements = (
            ('address', self.trustee_address),  # Trustee address
            ('address', self.target_address),  # Target address
            ('uint256', self.value),  # Value of the transaction
            ('bytes', self.data),  # Transaction data
            ('uint256', self.nonce)  # MultiSig nonce
        )

        packed_elements = b''.join([encode_single_packed(t, e) for t, e in typed_elements])
        return packed_elements

    def write(self, filepath: str = None) -> str:
        elements = vars(self)  # TODO: @kprasch, @jmyles  wdyt of using vars here?
        elements['data'] = elements['data'].hex()
        elements['digest'] = elements['digest'].hex()
        with open(filepath, 'w') as file:
            json.dump(elements, file)
        return filepath

    @classmethod
    def from_file(cls, filepath: str = None) -> 'Proposal':
        with open(filepath) as json_file:
            elements = json.load(json_file)
        elements['data'] = bytes.fromhex(elements['data'])
        elements['digest'] = bytes.fromhex(elements['digest'])

        instance = cls(**elements)
        return instance


class Authorization:
    """
    An edict issued by an Executive authorizing the execution of a multisig
    transaction by the delegated trustee.
    """

    SignatureComponents = namedtuple('SignatureComponents', 'v r s')

    def __init__(self, trustee_address: str, signed_transaction_hash: bytes):
        self.trustee_address = trustee_address
        self.__data = signed_transaction_hash
        self.__r = None
        self.__s = None
        self.__v = None

    def __bytes__(self):
        pass

    def get_signature_components(self) -> SignatureComponents:
        components = self.SignatureComponents(v=self.__v, r=self.__r, s=self.__s)
        return components

    @property
    def id(self):
        # TODO - Unique ID
        pass

    def _serialize(self) -> bytes:
        #TODO: BSS
        pass

    @classmethod
    def _deserialize(cls, data: bytes) -> tuple:
        #TODO: BSS
        pass

    def _write(self, filepath: str = None) -> str:
        with open(filepath, 'wb') as file:
            # TODO: Serialize
            file.write(self.__data)
        return filepath

    @classmethod
    def from_file(cls, filepath: str = None) -> 'Authorization':
        with open(filepath, 'rb') as file:
            data = file.read()
            deserialized_data = cls._deserialize(data=data)
            trustee_address, presigned_transaction_hash = deserialized_data
        instance = cls(trustee_address=trustee_address,
                       signed_transaction_hash=presigned_transaction_hash)
        return instance


class ExecutiveBoard:
    """A collection of Executives plus a Trustee."""

    def __init__(self, executives: List['Executive']):
        self.executives = executives


