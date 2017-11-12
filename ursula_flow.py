"""Deploy contracts in tester.

A simple Python script to deploy contracts and then estimate gas for different methods.
"""
from populus import Project

TIMEOUT = 10
MINING_COEFF = [10 ** 5, 10 ** 7]
M = int(1e6)


def main():
    project = Project()

    chain_name = "tester"
    print("Make sure {} chain is running, you can connect to it, or you'll get timeout".format(chain_name))

    with project.get_chain(chain_name) as chain:
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
        tx = token.transact({'from': web3.eth.accounts[1]}).approve(
                escrow.address, 1000 * M)
        chain.wait.for_receipt(tx, timeout=TIMEOUT)
        tx = escrow.transact({'from': web3.eth.accounts[1]}).deposit(1000 * M)
        chain.wait.for_receipt(tx, timeout=TIMEOUT)
        tx = escrow.transact({'from': web3.eth.accounts[1]}).lock(1000 * M, 100)
        chain.wait.for_receipt(tx, timeout=TIMEOUT)
        print('Locked')

        print(escrow.call().getAllLockedTokens())
        print(escrow.call().getLockedTokens(web3.eth.accounts[1]))
        print(escrow.call().getLockedTokens(web3.eth.accounts[2]))

        print('All done')


if __name__ == "__main__":
    main()
