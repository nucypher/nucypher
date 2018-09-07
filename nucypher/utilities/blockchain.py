from typing import List


def token_airdrop(token_agent, amount: int, origin: str, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    def txs():
        for address in addresses:
            txhash = token_agent.contract.functions.transfer(address, amount).transact({'from': origin,
                                                                                        'gas': 2000000})
            yield txhash

    receipts = list()
    for tx in txs():    # One at a time
        receipt = token_agent.blockchain.wait_for_receipt(tx)
        receipts.append(receipt)
    return receipts
