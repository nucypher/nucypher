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

from bytestring_splitter import BytestringSplitter
from eth_abi.packed import encode_single_packed
from eth_account import Account
from typing import Any, Dict, Tuple
from web3 import Web3
from web3.contract import Contract, ContractFunction

from nucypher.blockchain.eth.agents import ContractAgency, MultiSigAgent


class Proposal:

    def __init__(self, trustee_address, target_address, value, data, nonce, digest):
        self.trustee_address = trustee_address
        self.target_address = target_address
        self.value = value
        self.data = data
        self.nonce = nonce
        self.digest = digest

    @classmethod
    def from_transaction(cls, transaction, multisig_agent, trustee_address: str):
        proposal_elements = dict(trustee_address=trustee_address,
                                 target_address=transaction['to'],
                                 value=transaction['value'],
                                 data=Web3.toBytes(hexstr=transaction['data']), # TODO: should use a blockchain client to get correct data
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

    def decode_transaction_data(self, contract: Contract = None, registry=None) -> Tuple[ContractFunction, Dict[str, Any]]:
        if self.data:
            if not contract:
                agent = ContractAgency.get_agent(MultiSigAgent, registry=registry)
                blockchain = agent.blockchain

                name, version, address, abi = registry.search(contract_address=self.target_address)
                contract = blockchain.client.w3.eth.contract(abi=abi,
                                                             address=address,
                                                             version=version,
                                                             ContractFactoryClass=blockchain._CONTRACT_FACTORY)
            contract_function, params = contract.decode_function_input(self.data)
            return contract_function, params
        else:
            raise ValueError("This proposed TX doesn't have data")

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

    SignatureComponents = namedtuple('SignatureComponents', 'r s v')

    splitter = BytestringSplitter((bytes, 32),  # r
                                  (bytes, 32),  # s
                                  (bytes, 1))   # v

    def __init__(self, r, s, v):
        if v[0] not in (27, 28):
            raise ValueError(f"Wrong v component: got {v[0]} but only 27 or 28 are valid values")
        self.components = self.SignatureComponents(r=r, s=s, v=v)

    def recover_executive_address(self, proposal: Proposal) -> str:
        signing_account = Account.recoverHash(message_hash=proposal.digest, signature=self.serialize())
        return signing_account

    def __bytes__(self):
        return self.serialize()

    def serialize(self) -> bytes:
        return self.components.r + self.components.s + self.components.v

    @classmethod
    def deserialize(cls, data: bytes) -> 'Authorization':
        r, s, v = cls.splitter(data)
        return cls(r=r, s=s, v=v)

    @classmethod
    def from_hex(cls, hexstr: str) -> 'Authorization':
        bytestr = Web3.toBytes(hexstr=hexstr)
        return cls.deserialize(bytestr)

    def _write(self, filepath: str) -> str:
        with open(filepath, 'wb') as file:
            file.write(self.serialize())
        return filepath

    @classmethod
    def from_file(cls, filepath: str) -> 'Authorization':
        with open(filepath, 'rb') as file:
            data = file.read()
        return cls.deserialize(data=data)
