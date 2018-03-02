"""
Deploy contracts in tester.

A simple Python script to deploy contracts and then contract.estimate gas for different methods.
"""

from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.escrow import Escrow
from nkms_eth.token import NuCypherKMSToken


def main():
    testerchain = TesterBlockchain()
    chain, web3 = testerchain.web3, testerchain.chain
    creator, ursula1, ursula2, ursula3, *everyone_else = web3.eth.accounts

    print("Web3 providers are", web3.providers)

    # Create an ERC20 token
    token = NuCypherKMSToken(blockchain=testerchain)

    # Creator deploys the escrow
    escrow = Escrow(blockchain=testerchain, token=token)

    # Creator deploys the policy manager
    policy_manager, txhash = chain.provider.get_or_deploy_contract(
        'PolicyManager', deploy_args=[token.contract.address, escrow.contract.address],
        deploy_transaction={'from': creator})
    tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait.for_receipt(tx)

    print("contract.estimate gas:")

    # Give rights for mining
    print("Giving rights for mining = " + str(token.contract.contract.estimateGas({'from': creator}).addMiner(escrow.contract.address)))
    tx = token.transact({'from': creator}).addMiner(escrow.contract.address)
    chain.wait.for_receipt(tx)

    # Give Ursula and Alice some coins
    print("Transfer tokens = " + str(token.contract.contract.estimateGas({'from': creator}).transfer(ursula1, 10000)))
    tx = token.transact({'from': creator}).transfer(ursula1, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula2, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula3, 10000)
    chain.wait.for_receipt(tx)

    # Ursula and Alice give Escrow rights to transfer
    print("Approving transfer = " + str(token.contract.estimateGas({'from': ursula1}).approve(escrow.contract.address, 1001)))
    tx = token.transact({'from': ursula1}).approve(escrow.contract.address, 1001)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': ursula2}).approve(escrow.contract.address, 501)v v c vc vngffffffff
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': ursula3}).approve(escrow.contract.address, 501)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    print("First deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula1}).deposit(1000, 1)))
    tx = escrow.transact({'from': ursula1}).deposit(1000, 1)
    chain.wait.for_receipt(tx)
    print("Second deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula2}).deposit(500, 1)))
    tx = escrow.transact({'from': ursula2}).deposit(500, 1)
    chain.wait.for_receipt(tx)
    print("Third deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula3}).deposit(500, 1)))
    tx = escrow.transact({'from': ursula3}).deposit(500, 1)
    chain.wait.for_receipt(tx)

    # Wait 1 period and confirm activity
    testerchain.wait_time(1)
    print("First confirm activity = " + str(escrow.contract.estimateGas({'from': ursula1}).confirmActivity()))
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Second confirm activity = " + str(escrow.contract.estimateGas({'from': ursula2}).confirmActivity()))
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Third confirm activity = " + str(escrow.contract.estimateGas({'from': ursula3}).confirmActivity()))
    tx = escrow.transact({'from': ursula3}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Wait 1 period and mint tokens
    testerchain.wait_time(1)
    print("First mining = " + str(escrow.contract.estimateGas({'from': ursula1}).mint()))
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait.for_receipt(tx)
    print("Second mining = " + str(escrow.contract.estimateGas({'from': ursula2}).mint()))
    tx = escrow.transact({'from': ursula2}).mint()
    chain.wait.for_receipt(tx)
    print("Third/last mining = " + str(escrow.contract.estimateGas({'from': ursula3}).mint()))
    tx = escrow.transact({'from': ursula3}).mint()
    chain.wait.for_receipt(tx)

    # Confirm again
    print("First confirm activity again = " + str(escrow.contract.estimateGas({'from': ursula1}).confirmActivity()))
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Second confirm activity again = " + str(escrow.contract.estimateGas({'from': ursula2}).confirmActivity()))
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Third confirm activity again = " + str(escrow.contract.estimateGas({'from': ursula3}).confirmActivity()))
    tx = escrow.transact({'from': ursula3}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Get locked tokens
    print("Getting locked tokens = " + str(escrow.contract.estimateGas().getLockedTokens(ursula1)))
    print("Calculating locked tokens = " + str(escrow.contract.estimateGas().calculateLockedTokens(ursula1, 1)))

    # Switch to unlock and lock tokens again
    print("First switch = " + str(escrow.contract.estimateGas({'from': ursula1}).switchLock()))
    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait.for_receipt(tx)
    print("Second switch = " + str(escrow.contract.estimateGas({'from': ursula2}).switchLock()))
    tx = escrow.transact({'from': ursula2}).switchLock()
    chain.wait.for_receipt(tx)
    print("Third switch = " + str(escrow.contract.estimateGas({'from': ursula3}).switchLock()))
    tx = escrow.transact({'from': ursula3}).switchLock()
    chain.wait.for_receipt(tx)
    #
    testerchain.wait_time(1)
    print("First locking tokens = " + str(escrow.contract.estimateGas({'from': ursula1}).lock(1, 0)))
    tx = escrow.transact({'from': ursula1}).lock(1, 0)
    chain.wait.for_receipt(tx)
    print("Second locking tokens = " + str(escrow.contract.estimateGas({'from': ursula2}).lock(1, 0)))
    tx = escrow.transact({'from': ursula2}).lock(1, 0)
    chain.wait.for_receipt(tx)
    print("Third locking tokens = " + str(escrow.contract.estimateGas({'from': ursula3}).lock(1, 0)))
    tx = escrow.transact({'from': ursula3}).lock(1, 0)
    chain.wait.for_receipt(tx)

    # Wait 1 period and withdraw tokens
    testerchain.wait_time(1)
    print("First withdraw = " + str(escrow.contract.estimateGas({'from': ursula1}).withdraw(1)))
    tx = escrow.transact({'from': ursula1}).withdraw(1)
    chain.wait.for_receipt(tx)
    print("Second withdraw = " + str(escrow.contract.estimateGas({'from': ursula2}).withdraw(1)))
    tx = escrow.transact({'from': ursula2}).withdraw(1)
    chain.wait.for_receipt(tx)
    print("Third withdraw = " + str(escrow.contract.estimateGas({'from': ursula3}).withdraw(1)))
    tx = escrow.transact({'from': ursula3}).withdraw(1)
    chain.wait.for_receipt(tx)

    # Wait 1 period and confirm activity
    testerchain.wait_time(1)
    print("First confirm activity after downtime = " + str(escrow.contract.estimateGas({'from': ursula1}).confirmActivity()))
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Second confirm activity after downtime  = " + str(escrow.contract.estimateGas({'from': ursula2}).confirmActivity()))
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait.for_receipt(tx)
    print("Third confirm activity after downtime  = " + str(escrow.contract.estimateGas({'from': ursula3}).confirmActivity()))
    tx = escrow.transact({'from': ursula3}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula and Alice deposit some tokens to the escrow again
    print("First deposit tokens again = " + str(escrow.contract.estimateGas({'from': ursula1}).deposit(1, 1)))
    tx = escrow.transact({'from': ursula1}).deposit(1, 1)
    chain.wait.for_receipt(tx)
    print("Second deposit tokens again = " + str(escrow.contract.estimateGas({'from': ursula2}).deposit(1, 1)))
    tx = escrow.transact({'from': ursula2}).deposit(1, 1)
    chain.wait.for_receipt(tx)
    print("Third deposit tokens again = " + str(escrow.contract.estimateGas({'from': ursula3}).deposit(1, 1)))
    tx = escrow.transact({'from': ursula3}).deposit(1, 1)
    chain.wait.for_receipt(tx)

    # Wait 1 period and mint tokens
    testerchain.wait_time(1)
    print("First mining again = " + str(escrow.contract.estimateGas({'from': ursula1}).mint()))
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait.for_receipt(tx)
    print("Second mining again = " + str(escrow.contract.estimateGas({'from': ursula2}).mint()))
    tx = escrow.transact({'from': ursula2}).mint()
    chain.wait.for_receipt(tx)
    print("Third/last mining again = " + str(escrow.contract.estimateGas({'from': ursula3}).mint()))
    tx = escrow.transact({'from': ursula3}).mint()
    chain.wait.for_receipt(tx)

    print("All done!")


if __name__ == "__main__":
    main()
