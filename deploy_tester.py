"""Deploy contracts in tester.

A simple Python script to deploy contracts and then estimate gas for different methods.
"""
from populus import Project
from populus.utils.wait import wait_for_transaction_receipt
from web3 import Web3


def check_succesful_tx(web3: Web3, txid: str, timeout=180) -> dict:
    """See if transaction went through (Solidity code did not throw).

    :return: Transaction receipt
    """

    # http://ethereum.stackexchange.com/q/6007/620
    receipt = wait_for_transaction_receipt(web3, txid, timeout=timeout)
    txinfo = web3.eth.getTransaction(txid)

    # EVM has only one error mode and it's consume all gas
    assert txinfo["gas"] != receipt["gasUsed"]
    return receipt


def main():

    project = Project()

    chain_name = "tester"
    print("Make sure {} chain is running, you can connect to it, or you'll get timeout".format(chain_name))

    with project.get_chain(chain_name) as chain:
        web3 = chain.web3
        print("Web3 providers are", web3.providers)
        creator = web3.eth.accounts[0]
        ursula = web3.eth.accounts[1]
        alice = web3.eth.accounts[2]

        # Create an ERC20 token
        token, txhash = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                10 ** 9, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={
                'from': creator})
        check_succesful_tx(web3, txhash)
        print("Deploying HumanStandardToken, tx hash is", txhash)

        # Creator deploys the escrow
        escrow, txhash = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address, 1000],
            deploy_transaction={'from': creator})
        check_succesful_tx(web3, txhash)
        print("Deploying Escrow, tx hash is", txhash)

        # Give Ursula and Alice some coins
        tx = token.transact({'from': creator}).transfer(ursula, 10000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': creator}).transfer(alice, 10000)
        chain.wait.for_receipt(tx)
        print("Estimate gas for checking balance = " + str(token.estimateGas().balanceOf(alice)))

        # Ursula and Alice give Escrow rights to transfer
        print("Estimate gas for approving = " +
              str(token.estimateGas({'from': ursula}).approve(escrow.address, 1000)))
        tx = token.transact({'from': ursula}).approve(escrow.address, 1000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': alice}).approve(escrow.address, 500)
        chain.wait.for_receipt(tx)

        # Ursula and Alice transfer some tokens to the escrow
        print("Estimate gas for deposit = " +
              str(escrow.estimateGas({'from': ursula}).deposit(1000)))
        tx = escrow.transact({'from': ursula}).deposit(1000)
        chain.wait.for_receipt(tx)
        tx = escrow.transact({'from': alice}).deposit(500)
        chain.wait.for_receipt(tx)

        # Ursula and Alice lock some tokens for 100 and 200 blocks
        print("Estimate gas for locking = " +
              str(escrow.estimateGas({'from': ursula}).lock(500, 100)))
        tx = escrow.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)
        tx = escrow.transact({'from': alice}).lock(100, 200)
        chain.wait.for_receipt(tx)

        # Wait 150 blocks and mine tokens
        chain.wait.for_block(web3.eth.blockNumber + 150)
        print("Estimate gas for mining = " +
              str(escrow.estimateGas({'from': creator}).mine()))
        tx = escrow.transact({'from': creator}).mine()
        chain.wait.for_receipt(tx)

        # Wait 100 blocks and mine tokens
        chain.wait.for_block(web3.eth.blockNumber + 100)
        print("Estimate gas for mining = " +
              str(escrow.estimateGas({'from': creator}).mine()))
        tx = escrow.transact({'from': creator}).mine()
        chain.wait.for_receipt(tx)

        # Creator deploys the wallet manager
        wallet_manager, txhash = chain.provider.get_or_deploy_contract(
            'WalletManager', deploy_args=[token.address, 1000],
            deploy_transaction={'from': creator})
        check_succesful_tx(web3, txhash)
        print("Deploying WalletManager, tx hash is", txhash)

        print("Estimate gas for creating wallet = " +
              str(wallet_manager.estimateGas({'from': ursula}).createWallet()))
        contract_factory = chain.provider.get_contract_factory("Wallet")
        tx = wallet_manager.transact({'from': ursula}).createWallet()
        chain.wait.for_receipt(tx)
        ursula_wallet = contract_factory(address=wallet_manager.call().wallets(ursula))
        tx = wallet_manager.transact({'from': alice}).createWallet()
        chain.wait.for_receipt(tx)
        alice_wallet = contract_factory(address=wallet_manager.call().wallets(alice))

        # Give Ursula and Alice some coins
        tx = token.transact({'from': creator}).transfer(ursula, 10000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': creator}).transfer(alice, 10000)
        chain.wait.for_receipt(tx)

        # Ursula and Alice transfer some money to wallets
        print("Estimate gas for deposit = " +
              str(token.estimateGas({'from': ursula}).transfer(ursula_wallet.address, 1000)))
        tx = token.transact({'from': ursula}).transfer(ursula_wallet.address, 1000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': alice}).transfer(alice_wallet.address, 500)
        chain.wait.for_receipt(tx)

        # Ursula and Alice lock some tokens for 100 and 200 blocks
        print("Estimate gas for locking = " +
              str(ursula_wallet.estimateGas({'from': ursula}).lock(500, 100)))
        tx = ursula_wallet.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)
        tx = alice_wallet.transact({'from': alice}).lock(100, 200)
        chain.wait.for_receipt(tx)

        # Give manager some coins
        tx = token.transact({'from': creator}).transfer(wallet_manager.address, 10000)
        chain.wait.for_receipt(tx)

        # Wait 150 blocks and mine tokens
        chain.wait.for_block(web3.eth.blockNumber + 150)
        print("Estimate gas for mining = " +
              str(wallet_manager.estimateGas({'from': creator}).mine()))
        tx = wallet_manager.transact({'from': creator}).mine()
        chain.wait.for_receipt(tx)

        # Wait 100 blocks and mine tokens
        chain.wait.for_block(web3.eth.blockNumber + 100)
        print("Estimate gas for mining = " +
              str(wallet_manager.estimateGas({'from': creator}).mine()))
        tx = wallet_manager.transact({'from': creator}).mine()
        chain.wait.for_receipt(tx)

        print("All done!")


if __name__ == "__main__":
    main()
