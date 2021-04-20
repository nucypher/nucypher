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

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.utils import etherscan_url


def paint_decoded_transaction(emitter, proposal, contract, registry):
    emitter.echo("Decoded transaction:\n")
    contract_function, params = proposal.decode_transaction_data(contract, registry)
    emitter.echo(str(contract_function), color='yellow', bold=True)
    for param, value in params.items():
        emitter.echo(f"  {param}", color='green', nl=False)
        emitter.echo(" = ", nl=False)
        emitter.echo(str(value), color='green')
    emitter.echo()


def paint_receipt_summary(emitter, receipt, chain_name: str = None, transaction_type=None, provider_uri: str = None):
    tx_hash = receipt['transactionHash'].hex()
    emitter.echo("OK", color='green', nl=False, bold=True)
    if transaction_type:
        emitter.echo(f" | {transaction_type} | {tx_hash}", color='yellow', nl=False)
    else:
        emitter.echo(f" | {tx_hash}", color='yellow', nl=False)
    emitter.echo(f" ({receipt['gasUsed']} gas)")
    emitter.echo(f"Block #{receipt['blockNumber']} | {receipt['blockHash'].hex()}")

    if not chain_name:
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        chain_name = blockchain.client.chain_name
    try:
        url = etherscan_url(item=tx_hash, network=chain_name)
    except ValueError as e:
        emitter.log.info("Failed Etherscan URL construction: " + str(e))
    else:
        emitter.echo(f" See {url}\n")
