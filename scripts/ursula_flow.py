from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.escrow import Escrow
from nkms_eth.token import NuCypherKMSToken
from nkms_eth.miner import Miner


def main():
    testerchain = TesterBlockchain()

    print("Web3 providers -> ", testerchain.chain.web3.providers)
    creator, *addresses = testerchain.chain.web3.eth.accounts
    # ursula, alice, *everyone_else = addresses

    # Create NC ERC20 token
    token = NuCypherKMSToken(blockchain=testerchain)

    # Prepare escrow and miner
    escrow = Escrow(blockchain=testerchain, token=token)
    miner = Miner(blockchain=testerchain, token=token, escrow=escrow)

    # Airdropping
    token._airdrop()

    # Locking
    for address in addresses:
        miner.lock(address=address, amount=1000*NuCypherKMSToken.M, locktime=100)

    # Select random miners
    miners = escrow.sample()
    print(miners)


if __name__ == "__main__":
    main()
