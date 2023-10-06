


from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.utils import etherscan_url


def paint_receipt_summary(
    emitter,
    receipt,
    chain_name: str = None,
    transaction_type=None,
    blockchain_endpoint: str = None,
):
    tx_hash = receipt["transactionHash"].hex()
    emitter.echo("OK", color="green", nl=False, bold=True)
    if transaction_type:
        emitter.echo(f" | {transaction_type} | {tx_hash}", color='yellow', nl=False)
    else:
        emitter.echo(f" | {tx_hash}", color='yellow', nl=False)
    emitter.echo(f" ({receipt['gasUsed']} gas)")
    emitter.echo(f"Block #{receipt['blockNumber']} | {receipt['blockHash'].hex()}")

    if not chain_name:
        blockchain = BlockchainInterfaceFactory.get_interface(
            endpoint=blockchain_endpoint
        )
        chain_name = blockchain.client.chain_name
    try:
        url = etherscan_url(item=tx_hash, network=chain_name)
    except ValueError as e:
        emitter.log.info("Failed Etherscan URL construction: " + str(e))
    else:
        emitter.echo(f" See {url}\n")
