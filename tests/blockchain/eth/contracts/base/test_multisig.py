import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address


def sign_hash(testerchain, account: str, data_hash: bytes) -> dict:
    provider = testerchain.interface.providers[0]
    address = to_canonical_address(account)
    key = provider.ethereum_tester.backend._key_lookup[address]._raw_key
    signed_data = testerchain.interface.w3.eth.account.signHash(data_hash, key)
    return signed_data


def to_32byte_hex(w3, value):
    return w3.toHex(w3.toBytes(value).rjust(32, b'\0'))


@pytest.mark.slow
def test_execute(testerchain):
    w3 = testerchain.interface.w3
    accounts = sorted(testerchain.interface.w3.eth.accounts)
    owners = accounts[0:5]
    others = accounts[5:]
    NULL_ADDR = '0x' + '0' * 40
    token, _ = testerchain.interface.deploy_contract('NuCypherToken', 2 * 10 ** 40)

    # Can't create the contract with the address 0x0 (address 0x0 is restricted for use)
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.interface.deploy_contract('MultiSig', 3, owners + [NULL_ADDR])
    # Owners must be no less than the threshold value
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.interface.deploy_contract('MultiSig', 6, owners)
    # Can't use the same owners multiple times in the constructor (the owner array must contain unique values)
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.interface.deploy_contract('MultiSig', 2, [owners[0], owners[1], owners[1]])
    # The threshold must be greater than zero or the contract will be broken
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.interface.deploy_contract('MultiSig', 0, owners)
    multisig, _ = testerchain.interface.deploy_contract('MultiSig', 3, owners)

    # Check owners status
    assert multisig.functions.isOwner(owners[0]).call()
    assert multisig.functions.isOwner(owners[1]).call()
    assert not multisig.functions.isOwner(others[0]).call()
    assert not multisig.functions.isOwner(others[1]).call()

    # Transfer ETH to the multisig contract
    tx = testerchain.interface.w3.eth.sendTransaction(
        {'from': testerchain.interface.w3.eth.coinbase, 'to': multisig.address, 'value': 200})
    testerchain.wait_for_receipt(tx)
    assert 200 == w3.eth.getBalance(multisig.address)

    # Prepare data
    nonce = multisig.functions.nonce().call()
    tx_hash = multisig.functions.getUnsignedTransactionHash(others[0], 100, w3.toBytes(0), nonce).call()
    signed_tx_hash_0 = sign_hash(testerchain, owners[0], tx_hash)
    signed_tx_hash_1 = sign_hash(testerchain, owners[1], tx_hash)
    signed_tx_hash_2 = sign_hash(testerchain, owners[2], tx_hash)
    signed_tx_hash_3 = sign_hash(testerchain, owners[3], tx_hash)
    signed_tx_hash_bad = sign_hash(testerchain, others[0], tx_hash)
    balance = w3.eth.getBalance(others[0])

    # Must be exact 3 (threshold) signatures
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v, signed_tx_hash_3.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
             to_32byte_hex(w3, signed_tx_hash_2.r), to_32byte_hex(w3, signed_tx_hash_3.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
             to_32byte_hex(w3, signed_tx_hash_2.s), to_32byte_hex(w3, signed_tx_hash_3.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    # Only owners can sign transactions
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_bad.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
             to_32byte_hex(w3, signed_tx_hash_bad.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
             to_32byte_hex(w3, signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    # All owners must sign the same transaction
    tx_hash_bad = multisig.functions.getUnsignedTransactionHash(others[0], 100, w3.toBytes(0), nonce + 1).call()
    signed_tx_hash_bad = sign_hash(testerchain, owners[0], tx_hash_bad)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_bad.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
             to_32byte_hex(w3, signed_tx_hash_bad.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
             to_32byte_hex(w3, signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    # The owner's signatures must be in ascending order of addresses (function restrictions)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_1.v, signed_tx_hash_2.v, signed_tx_hash_0.v],
            [to_32byte_hex(w3, signed_tx_hash_1.r), to_32byte_hex(w3, signed_tx_hash_2.r),
             to_32byte_hex(w3, signed_tx_hash_0.r)],
            [to_32byte_hex(w3, signed_tx_hash_1.s), to_32byte_hex(w3, signed_tx_hash_2.s),
             to_32byte_hex(w3, signed_tx_hash_0.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    # Can't use wrong signatures (one of S value is wrong)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
             to_32byte_hex(w3, signed_tx_hash_2.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
             to_32byte_hex(w3, signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    assert balance == w3.eth.getBalance(others[0])
    assert 200 == w3.eth.getBalance(multisig.address)
    tx = multisig.functions.execute(
        [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
        [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
         to_32byte_hex(w3, signed_tx_hash_2.r)],
        [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
         to_32byte_hex(w3, signed_tx_hash_2.s)],
        others[0],
        100,
        w3.toBytes(0)
    ).transact()
    testerchain.wait_for_receipt(tx)
    assert balance + 100 == w3.eth.getBalance(others[0])
    assert 100 == w3.eth.getBalance(multisig.address)

    # Can't use the same signatures again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
            [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
             to_32byte_hex(w3, signed_tx_hash_2.r)],
            [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
             to_32byte_hex(w3, signed_tx_hash_2.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact()
        testerchain.wait_for_receipt(tx)

    # Transfer tokens to the multisig contract
    tx = token.functions.transfer(multisig.address, 100).transact()
    testerchain.wait_for_receipt(tx)
    assert 100 == token.functions.balanceOf(multisig.address).call()

    # Prepare transaction
    nonce = multisig.functions.nonce().call()
    tx = token.functions.transfer(owners[0], 100).buildTransaction()
    tx_hash = multisig.functions.getUnsignedTransactionHash(token.address, 0, tx['data'], nonce).call()
    signed_tx_hash_0 = sign_hash(testerchain, owners[0], tx_hash)
    signed_tx_hash_1 = sign_hash(testerchain, owners[3], tx_hash)
    signed_tx_hash_2 = sign_hash(testerchain, owners[4], tx_hash)
    tx = multisig.functions.execute(
        [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
        [to_32byte_hex(w3, signed_tx_hash_0.r), to_32byte_hex(w3, signed_tx_hash_1.r),
         to_32byte_hex(w3, signed_tx_hash_2.r)],
        [to_32byte_hex(w3, signed_tx_hash_0.s), to_32byte_hex(w3, signed_tx_hash_1.s),
         to_32byte_hex(w3, signed_tx_hash_2.s)],
        token.address,
        0,
        tx['data']
    ).transact()
    testerchain.wait_for_receipt(tx)
    assert 100 == token.functions.balanceOf(owners[0]).call()
    assert 0 == token.functions.balanceOf(multisig.address).call()
