#!/usr/bin/env python3

"""Deploy contracts in tester.

A simple Python script to deploy contracts and then estimate gas for different methods.
"""
import random
from nkms_eth.blockchain import project

TIMEOUT = 10
MINING_COEFF = [10 ** 5, 10 ** 7]
M = int(1e6)
NULL_ADDR = '0x' + '0' * 40


def main():
    proj = project()

    chain_name = "tester"
    print("Make sure {} chain is running, you can connect to it, or you'll get timeout".format(chain_name))

    with proj.get_chain(chain_name) as chain:
        web3 = chain.web3
        print("Web3 providers are", web3.providers)
        creator = web3.eth.accounts[0]
        # ursula = web3.eth.accounts[1]
        # alice = web3.eth.accounts[2]

        # Create an ERC20 token
        token, tx = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                int(1e9) * M, int(1e10) * M, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={
                'from': creator})
        chain.wait.for_receipt(tx, timeout=TIMEOUT)
        print("Deployed HumanStandardToken, tx hash is", tx)

        escrow, tx = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address] + MINING_COEFF,
            deploy_transaction={'from': creator})
        chain.wait.for_receipt(tx, timeout=TIMEOUT)
        print("Deployed escrow, tx hash is", tx)

        # debug airdrop
        txs = [
                token.transact({'from': creator}).transfer(account, 10000 * M)
                for account in web3.eth.accounts[1:]]
        for tx in txs:
            chain.wait.for_receipt(tx, timeout=TIMEOUT)
        print('Airdrop done')

        # Test locking
        for addr in web3.eth.accounts[1:]:
            tx = token.transact({'from': addr}).approve(
                    escrow.address, 1000 * M)
            chain.wait.for_receipt(tx, timeout=TIMEOUT)
            tx = escrow.transact({'from': addr}).deposit(1000 * M, 100)
            chain.wait.for_receipt(tx, timeout=TIMEOUT)

        n_tokens = escrow.call().getAllLockedTokens()
        print('Locked', n_tokens)

        print(web3.eth.accounts[1])
        print(web3.eth.accounts[-1])
        address_stop, shift = escrow.call().findCumSum(NULL_ADDR, n_tokens // 3)
        print(address_stop, shift)

        # Experimenting with distributions of random points
        n_ursulas = 5
        n_select = int(n_ursulas * 1.7)  # Select more ursulas
        points = [0] + sorted(random.randrange(n_tokens) for _ in
                              range(n_select))
        deltas = [i - j for i, j in zip(points[1:], points[:-1])]
        addrs = set()
        addr = NULL_ADDR
        shift = 0
        for delta in deltas:
            addr, shift = escrow.call().findCumSum(addr, delta + shift)
            addrs.add(addr)
        addrs = random.sample(addrs, n_ursulas)
        print(addrs)


if __name__ == "__main__":
    main()
