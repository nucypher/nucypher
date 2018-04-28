#!/usr/bin/env python3

"""
Deploy contracts in tester.
A simple Python script to deploy contracts and then estimate gas for different methods.
"""


from nkms.blockchain.eth.agents import NuCypherKMSTokenAgent, MinerAgent
import os

from tests.utilities import TesterBlockchain


def main():
    chain = TesterBlockchain()
    web3 = chain.web3
    creator, ursula1, ursula2, ursula3, alice1, *everyone_else = web3.eth.accounts

    print("Web3 providers are", web3.providers)

    # TODO: Updatae to agents and deployers
    # Create an ERC20 token
    token = NuCypherKMSToken(blockchain=chain)
    token.arm()
    token.deploy()

    # Creator deploys the escrow
    escrow = Escrow(blockchain=chain, token=token)
    escrow.arm()
    escrow.deploy()

    # Creator deploys the policy manager
    policy_manager, txhash = chain.provider.get_or_deploy_contract(
        'PolicyManager', deploy_args=[escrow.contract.address],
        deploy_transaction={'from': creator})
    tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait.for_receipt(tx)

    print("Estimate gas:")
    # Pre deposit tokens
    tx = token.transact({'from': creator}).approve(escrow.contract.address, 10 ** 7)
    chain.wait.for_receipt(tx)
    print("Pre-deposit tokens for 5 owners = " +
          str(escrow.contract.estimateGas({'from': creator}).preDeposit(
              web3.eth.accounts[4:9], [10 ** 6] * 5, [1] * 5)))

    # Give Ursula and Alice some coins
    print("Transfer tokens = " + str(token.contract.estimateGas({'from': creator}).transfer(ursula1, 10 ** 7)))
    tx = token.transact({'from': creator}).transfer(ursula1, 10 ** 7)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula2, 10 ** 7)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula3, 10 ** 7)
    chain.wait.for_receipt(tx)

    # Ursula and Alice give Escrow rights to transfer
    print("Approving transfer = " +
          str(token.contract.estimateGas({'from': ursula1}).approve(escrow.contract.address, 5 * 10 ** 6 + 1)))
    tx = token.transact({'from': ursula1}).approve(escrow.contract.address, 5 * 10 ** 6 + 1)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': ursula2}).approve(escrow.contract.address, 2 * 10 ** 6 + 1)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': ursula3}).approve(escrow.contract.address, 2 * 10 ** 6 + 1)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    print("First deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula1}).deposit(5 * 10 ** 6, 1)))
    tx = escrow.transact({'from': ursula1}).deposit(5 * 10 ** 6, 1)
    chain.wait.for_receipt(tx)
    print("Second deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula2}).deposit(2 * 10 ** 6, 1)))
    tx = escrow.transact({'from': ursula2}).deposit(2 * 10 ** 6, 1)
    chain.wait.for_receipt(tx)
    print("Third deposit tokens = " + str(escrow.contract.estimateGas({'from': ursula3}).deposit(2 * 10 ** 6, 1)))
    tx = escrow.transact({'from': ursula3}).deposit(2 * 10 ** 6, 1)
    chain.wait.for_receipt(tx)

    # Wait 1 period and confirm activity
    chain.time_travel(1)
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
    chain.time_travel(1)
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
    chain.time_travel(1)
    print("First locking tokens = " + str(escrow.contract.estimateGas({'from': ursula1}).lock(10 ** 6, 0)))
    tx = escrow.transact({'from': ursula1}).lock(10 ** 6, 0)
    chain.wait.for_receipt(tx)
    print("Second locking tokens = " + str(escrow.contract.estimateGas({'from': ursula2}).lock(10 ** 6, 0)))
    tx = escrow.transact({'from': ursula2}).lock(10 ** 6, 0)
    chain.wait.for_receipt(tx)
    print("Third locking tokens = " + str(escrow.contract.estimateGas({'from': ursula3}).lock(10 ** 6, 0)))
    tx = escrow.transact({'from': ursula3}).lock(10 ** 6, 0)
    chain.wait.for_receipt(tx)

    # Wait 1 period and withdraw tokens
    chain.time_travel(1)
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
    chain.time_travel(1)
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
    chain.time_travel(1)
    print("First mining again = " + str(escrow.contract.estimateGas({'from': ursula1}).mint()))
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait.for_receipt(tx)
    print("Second mining again = " + str(escrow.contract.estimateGas({'from': ursula2}).mint()))
    tx = escrow.transact({'from': ursula2}).mint()
    chain.wait.for_receipt(tx)
    print("Third/last mining again = " + str(escrow.contract.estimateGas({'from': ursula3}).mint()))
    tx = escrow.transact({'from': ursula3}).mint()
    chain.wait.for_receipt(tx)

    # Create policy
    policy_id_1 = os.urandom(20)
    policy_id_2 = os.urandom(20)
    number_of_periods = 10
    print("First creating policy (1 node, 10 periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_1, number_of_periods, [ursula1])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000})\
        .createPolicy(policy_id_1, number_of_periods, [ursula1])
    chain.wait.for_receipt(tx)
    print("Second creating policy (1 node, 10 periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_2, number_of_periods, [ursula1])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000}) \
        .createPolicy(policy_id_2, number_of_periods, [ursula1])
    chain.wait.for_receipt(tx)

    # Revoke policy
    print("Revoking policy = " +
          str(policy_manager.estimateGas({'from': alice1}).revokePolicy(policy_id_1)))
    tx = policy_manager.transact({'from': alice1}).revokePolicy(policy_id_1)
    chain.wait.for_receipt(tx)
    tx = policy_manager.transact({'from': alice1}).revokePolicy(policy_id_2)
    chain.wait.for_receipt(tx)

    # Create policy with more periods
    policy_id_1 = os.urandom(20)
    policy_id_2 = os.urandom(20)
    policy_id_3 = os.urandom(20)
    number_of_periods = 100
    print("First creating policy (1 node, " + str(number_of_periods) + " periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_1, number_of_periods, [ursula2])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000})\
        .createPolicy(policy_id_1, number_of_periods, [ursula2])
    chain.wait.for_receipt(tx)
    chain.time_travel(1)
    print("Second creating policy (1 node, " + str(number_of_periods) + " periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_2, number_of_periods, [ursula2])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000}) \
        .createPolicy(policy_id_2, number_of_periods, [ursula2])
    chain.wait.for_receipt(tx)
    print("Third creating policy (1 node, " + str(number_of_periods) + " periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_3, number_of_periods, [ursula1])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000}) \
        .createPolicy(policy_id_3, number_of_periods, [ursula1])
    chain.wait.for_receipt(tx)

    # Mine and revoke policy
    chain.time_travel(10)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait.for_receipt(tx)

    chain.time_travel(1)
    print("First mining after downtime = " + str(escrow.contract.estimateGas({'from': ursula1}).mint()))
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait.for_receipt(tx)
    print("Second mining after downtime = " + str(escrow.contract.estimateGas({'from': ursula2}).mint()))
    tx = escrow.transact({'from': ursula2}).mint()
    chain.wait.for_receipt(tx)

    chain.time_travel(10)
    print("First revoking policy after downtime = " +
          str(policy_manager.estimateGas({'from': alice1}).revokePolicy(policy_id_1)))
    tx = policy_manager.transact({'from': alice1}).revokePolicy(policy_id_1)
    chain.wait.for_receipt(tx)
    print("Second revoking policy after downtime = " +
          str(policy_manager.estimateGas({'from': alice1}).revokePolicy(policy_id_2)))
    tx = policy_manager.transact({'from': alice1}).revokePolicy(policy_id_2)
    chain.wait.for_receipt(tx)
    print("Second revoking policy after downtime = " +
          str(policy_manager.estimateGas({'from': alice1}).revokePolicy(policy_id_3)))
    tx = policy_manager.transact({'from': alice1}).revokePolicy(policy_id_3)
    chain.wait.for_receipt(tx)

    # Create policy with multiple nodes
    policy_id_1 = os.urandom(20)
    policy_id_2 = os.urandom(20)
    policy_id_3 = os.urandom(20)
    number_of_periods = 100
    print("First creating policy (3 nodes, 100 periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 30000})
              .createPolicy(policy_id_1, number_of_periods, [ursula1, ursula2, ursula3])))
    tx = policy_manager.transact({'from': alice1, 'value': 30000}) \
        .createPolicy(policy_id_1, number_of_periods, [ursula1, ursula2, ursula3])
    chain.wait.for_receipt(tx)
    print("Second creating policy (3 nodes, 100 periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 10000})
              .createPolicy(policy_id_2, number_of_periods, [ursula1, ursula2, ursula3])))
    tx = policy_manager.transact({'from': alice1, 'value': 10000}) \
        .createPolicy(policy_id_2, number_of_periods, [ursula1, ursula2, ursula3])
    chain.wait.for_receipt(tx)
    print("Third creating policy (2 nodes, 100 periods) = " +
          str(policy_manager.estimateGas({'from': alice1, 'value': 20000})
              .createPolicy(policy_id_3, number_of_periods, [ursula1, ursula2])))
    tx = policy_manager.transact({'from': alice1, 'value': 20000}) \
        .createPolicy(policy_id_3, number_of_periods, [ursula1, ursula2])
    chain.wait.for_receipt(tx)

    print("All done!")


if __name__ == "__main__":
    main()