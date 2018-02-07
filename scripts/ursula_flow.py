from nkms_eth.blockchain import TesterBlockchain
from nkms_eth.escrow import Escrow
from nkms_eth.token import NuCypherKMSToken
from nkms_eth.miner import Miner


def main():
    blockchain = TesterBlockchain()
    with blockchain as chain:
        print("Web3 providers -> ", chain.web3.providers)
        creator, *addresses = chain.web3.eth.accounts
        # ursula, alice, *everyone_else = addresses

        # Create NC ERC20 token
        token = NuCypherKMSToken(blockchain=blockchain)

        # Prepare escrow and miner
        escrow = Escrow(blockchain=blockchain, token=token)
        miner = Miner(blockchain=blockchain, token=token, escrow=escrow)

        # Airdropping
        token.airdrop()

        # Locking
        for address in addresses:
            miner.lock(address=address, amount=1000*NuCypherKMSToken.M, locktime=100)

        # Select random miners
        miners = escrow.sample()
        print(miners)


if __name__ == "__main__":
    main()
