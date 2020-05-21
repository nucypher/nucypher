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
from web3.main import Web3

from nucypher.blockchain.eth.token import NU
from nucypher.cli.painting.transactions import paint_decoded_transaction


def paint_multisig_contract_info(emitter, multisig_agent, token_agent):

    sep = '-' * 45
    emitter.echo(sep)

    blockchain = multisig_agent.blockchain
    registry = multisig_agent.registry

    contract_payload = f"""

* Web3 Provider
====================================================================

Provider URI ............. {blockchain.provider_uri}
Registry  ................ {registry.filepath}

* MultiSig Contract Information
=====================================================================

{multisig_agent.contract_name} ................. {multisig_agent.contract_address}
    ~ Ethers ............. {Web3.fromWei(blockchain.client.get_balance(multisig_agent.contract_address), 'ether')} ETH
    ~ Tokens ............. {NU.from_nunits(token_agent.get_balance(multisig_agent.contract_address))}"""
    emitter.echo(contract_payload)

    emitter.echo(f"Nonce .................... {multisig_agent.nonce}")
    emitter.echo(f"Threshold: ............... {multisig_agent.threshold}")
    emitter.echo(f"Owners:")
    for i, owner in enumerate(multisig_agent.owners):
        emitter.echo(f"[{i}] {owner}")


def paint_multisig_proposed_transaction(emitter, proposal, contract=None, registry=None):

    info = f"""
Trustee address: .... {proposal.trustee_address}
Target address: ..... {proposal.target_address}
Value: .............. {Web3.fromWei(proposal.value, 'ether')} ETH
Nonce: .............. {proposal.nonce}
Raw TX data: ........ {proposal.data.hex()}
Unsigned TX hash: ... {proposal.digest.hex()}
"""
    emitter.echo(info)

    if contract or registry:
        paint_decoded_transaction(emitter, proposal, contract, registry)
