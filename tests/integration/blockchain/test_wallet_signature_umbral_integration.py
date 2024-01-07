from nucypher_core.umbral import RecoverableSignature

from nucypher.blockchain.eth.wallets import Wallet
from nucypher.crypto.utils import verify_eip_191


def test_signature_umbral_integration(accounts, test_registry, testerchain):
    wallet = Wallet.from_key(accounts.ape_accounts[0].private_key)
    data_to_sign = b'Premium Select Luxury Pencil Holder'
    signature = wallet.sign_message(message=data_to_sign)
    RecoverableSignature.from_be_bytes(bytes(signature))
    is_verified = verify_eip_191(address=wallet.address, message=data_to_sign, signature=signature)
    assert is_verified is True
