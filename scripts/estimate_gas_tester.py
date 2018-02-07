"""Deploy contracts in tester.

A simple Python script to deploy contracts and then estimate gas for different methods.
"""
from nkms_eth.blockchain import project


def wait_time(chain, wait_hours):
    web3 = chain.web3
    step = 50
    end_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
    while web3.eth.getBlock(web3.eth.blockNumber).timestamp < end_timestamp:
        chain.wait.for_block(web3.eth.blockNumber + step)


def main():

    proj = project()

    chain_name = "tester"
    print("Make sure {} chain is running, you can connect to it, or you'll get timeout".format(chain_name))

    with proj.get_chain(chain_name) as chain:
        web3 = chain.web3
        print("Web3 providers are", web3.providers)
        creator = web3.eth.accounts[0]
        ursula1 = web3.eth.accounts[1]
        ursula2 = web3.eth.accounts[2]
        ursula3 = web3.eth.accounts[3]

        # Create an ERC20 token
        token, _ = chain.provider.get_or_deploy_contract(
            'NuCypherKMSToken', deploy_args=[2 * 10 ** 9],
            deploy_transaction={'from': creator})

        # Creator deploys the escrow
        escrow, _ = chain.provider.get_or_deploy_contract(
            'Escrow', deploy_args=[token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 1],
            deploy_transaction={'from': creator})

        # Creator deploys the policy manager
        policy_manager, _ = chain.provider.get_or_deploy_contract(
            'PolicyManager', deploy_args=[token.address, escrow.address],
            deploy_transaction={'from': creator})
        tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
        chain.wait.for_receipt(tx)

        # Give Escrow tokens for reward and initialize contract
        tx = token.transact({'from': creator}).transfer(escrow.address, 10 ** 9)
        chain.wait.for_receipt(tx)
        tx = escrow.transact().initialize()
        chain.wait.for_receipt(tx)

        print("Estimate gas:")

        # Give Ursula and Alice some coins
        print("Transfer tokens = " +
              str(token.estimateGas({'from': creator}).transfer(ursula1, 10000)))
        tx = token.transact({'from': creator}).transfer(ursula1, 10000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': creator}).transfer(ursula2, 10000)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': creator}).transfer(ursula3, 10000)
        chain.wait.for_receipt(tx)

        # Ursula and Alice give Escrow rights to transfer
        print("Approving transfer = " +
              str(token.estimateGas({'from': ursula1}).approve(escrow.address, 1001)))
        tx = token.transact({'from': ursula1}).approve(escrow.address, 1001)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': ursula2}).approve(escrow.address, 501)
        chain.wait.for_receipt(tx)
        tx = token.transact({'from': ursula3}).approve(escrow.address, 501)
        chain.wait.for_receipt(tx)

        # Ursula and Alice transfer some tokens to the escrow and lock them
        print("First deposit tokens = " +
              str(escrow.estimateGas({'from': ursula1}).deposit(1000, 1)))
        tx = escrow.transact({'from': ursula1}).deposit(1000, 1)
        chain.wait.for_receipt(tx)
        print("Second deposit tokens = " +
              str(escrow.estimateGas({'from': ursula2}).deposit(500, 1)))
        tx = escrow.transact({'from': ursula2}).deposit(500, 1)
        chain.wait.for_receipt(tx)
        print("Third deposit tokens = " +
              str(escrow.estimateGas({'from': ursula3}).deposit(500, 1)))
        tx = escrow.transact({'from': ursula3}).deposit(500, 1)
        chain.wait.for_receipt(tx)

        # Wait 1 period and confirm activity
        wait_time(chain, 1)
        print("First confirm activity = " +
              str(escrow.estimateGas({'from': ursula1}).confirmActivity()))
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Second confirm activity = " +
              str(escrow.estimateGas({'from': ursula2}).confirmActivity()))
        tx = escrow.transact({'from': ursula2}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Third confirm activity = " +
              str(escrow.estimateGas({'from': ursula3}).confirmActivity()))
        tx = escrow.transact({'from': ursula3}).confirmActivity()
        chain.wait.for_receipt(tx)

        # Wait 1 period and mint tokens
        wait_time(chain, 1)
        print("First mining = " +
              str(escrow.estimateGas({'from': ursula1}).mint()))
        tx = escrow.transact({'from': ursula1}).mint()
        chain.wait.for_receipt(tx)
        print("Second mining = " +
              str(escrow.estimateGas({'from': ursula2}).mint()))
        tx = escrow.transact({'from': ursula2}).mint()
        chain.wait.for_receipt(tx)
        print("Third/last mining = " +
              str(escrow.estimateGas({'from': ursula3}).mint()))
        tx = escrow.transact({'from': ursula3}).mint()
        chain.wait.for_receipt(tx)

        # Confirm again
        print("First confirm activity again = " +
              str(escrow.estimateGas({'from': ursula1}).confirmActivity()))
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Second confirm activity again = " +
              str(escrow.estimateGas({'from': ursula2}).confirmActivity()))
        tx = escrow.transact({'from': ursula2}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Third confirm activity again = " +
              str(escrow.estimateGas({'from': ursula3}).confirmActivity()))
        tx = escrow.transact({'from': ursula3}).confirmActivity()
        chain.wait.for_receipt(tx)

        # Get locked tokens
        print("Getting locked tokens = " +
              str(escrow.estimateGas().getLockedTokens(ursula1)))
        print("Calculating locked tokens = " +
              str(escrow.estimateGas().calculateLockedTokens(ursula1, 1)))

        # Switch to unlock and lock tokens again
        print("First switch = " +
              str(escrow.estimateGas({'from': ursula1}).switchLock()))
        tx = escrow.transact({'from': ursula1}).switchLock()
        chain.wait.for_receipt(tx)
        print("Second switch = " +
              str(escrow.estimateGas({'from': ursula2}).switchLock()))
        tx = escrow.transact({'from': ursula2}).switchLock()
        chain.wait.for_receipt(tx)
        print("Third switch = " +
              str(escrow.estimateGas({'from': ursula3}).switchLock()))
        tx = escrow.transact({'from': ursula3}).switchLock()
        chain.wait.for_receipt(tx)
        #
        wait_time(chain, 1)
        print("First locking tokens = " +
              str(escrow.estimateGas({'from': ursula1}).lock(1, 0)))
        tx = escrow.transact({'from': ursula1}).lock(1, 0)
        chain.wait.for_receipt(tx)
        print("Second locking tokens = " +
              str(escrow.estimateGas({'from': ursula2}).lock(1, 0)))
        tx = escrow.transact({'from': ursula2}).lock(1, 0)
        chain.wait.for_receipt(tx)
        print("Third locking tokens = " +
              str(escrow.estimateGas({'from': ursula3}).lock(1, 0)))
        tx = escrow.transact({'from': ursula3}).lock(1, 0)
        chain.wait.for_receipt(tx)

        # Wait 1 period and withdraw tokens
        wait_time(chain, 1)
        print("First withdraw = " +
              str(escrow.estimateGas({'from': ursula1}).withdraw(1)))
        tx = escrow.transact({'from': ursula1}).withdraw(1)
        chain.wait.for_receipt(tx)
        print("Second withdraw = " +
              str(escrow.estimateGas({'from': ursula2}).withdraw(1)))
        tx = escrow.transact({'from': ursula2}).withdraw(1)
        chain.wait.for_receipt(tx)
        print("Third withdraw = " +
              str(escrow.estimateGas({'from': ursula3}).withdraw(1)))
        tx = escrow.transact({'from': ursula3}).withdraw(1)
        chain.wait.for_receipt(tx)

        # Wait 1 period and confirm activity
        wait_time(chain, 1)
        print("First confirm activity after downtime = " +
              str(escrow.estimateGas({'from': ursula1}).confirmActivity()))
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Second confirm activity after downtime  = " +
              str(escrow.estimateGas({'from': ursula2}).confirmActivity()))
        tx = escrow.transact({'from': ursula2}).confirmActivity()
        chain.wait.for_receipt(tx)
        print("Third confirm activity after downtime  = " +
              str(escrow.estimateGas({'from': ursula3}).confirmActivity()))
        tx = escrow.transact({'from': ursula3}).confirmActivity()
        chain.wait.for_receipt(tx)

        # Ursula and Alice deposit some tokens to the escrow again
        print("First deposit tokens again = " +
              str(escrow.estimateGas({'from': ursula1}).deposit(1, 1)))
        tx = escrow.transact({'from': ursula1}).deposit(1, 1)
        chain.wait.for_receipt(tx)
        print("Second deposit tokens again = " +
              str(escrow.estimateGas({'from': ursula2}).deposit(1, 1)))
        tx = escrow.transact({'from': ursula2}).deposit(1, 1)
        chain.wait.for_receipt(tx)
        print("Third deposit tokens again = " +
              str(escrow.estimateGas({'from': ursula3}).deposit(1, 1)))
        tx = escrow.transact({'from': ursula3}).deposit(1, 1)
        chain.wait.for_receipt(tx)

        # Wait 1 period and mint tokens
        wait_time(chain, 1)
        print("First mining again = " +
              str(escrow.estimateGas({'from': ursula1}).mint()))
        tx = escrow.transact({'from': ursula1}).mint()
        chain.wait.for_receipt(tx)
        print("Second mining again = " +
              str(escrow.estimateGas({'from': ursula2}).mint()))
        tx = escrow.transact({'from': ursula2}).mint()
        chain.wait.for_receipt(tx)
        print("Third/last mining again = " +
              str(escrow.estimateGas({'from': ursula3}).mint()))
        tx = escrow.transact({'from': ursula3}).mint()
        chain.wait.for_receipt(tx)

        print("All done!")


if __name__ == "__main__":
    main()
