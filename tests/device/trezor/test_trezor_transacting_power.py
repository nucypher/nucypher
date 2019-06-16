from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.characters.base import Character
from nucypher.crypto.device.trezor import Trezor
from nucypher.crypto.powers import TransactingPower


def test_trezor_transacting_power_integration(testerchain):

    # Mock StakingEscrow for this test
    StakingEscrowAgent.__init__ = lambda *a, **kw: None

    trezor = Trezor()
    etherbase = trezor.get_address(index=0)

    transacting_power = TransactingPower(device=trezor)
    transacting_power.unlock_account(checksum_address=etherbase)

    # Set
    transactor = Character(is_me=True, checksum_address=etherbase)
    transactor._crypto_power.consume_power_up(transacting_power)

    # Get
    power = transactor._crypto_power.power_ups(TransactingPower)
    assert power == transacting_power

    signature = power.sign_message(message='Through the transitive nightfall of diamonds',
                                   checksum_address=etherbase)
    assert isinstance(signature, bytes)

    # As they come from web3.py
    transaction = dict(nonce=0,
                       gasPrice=1,
                       gas=100000,
                       to='0x950041c1599529a9f64cf2be59ffb86072f00111',
                       value=1,
                       data=b'')

    signed_transaction = power.sign_transaction(unsigned_transaction=transaction, checksum_address=etherbase)

    assert True
