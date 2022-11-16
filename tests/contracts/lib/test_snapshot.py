

import itertools

import pytest
from web3 import Web3


@pytest.fixture(scope='module')
def snapshot(testerchain, deploy_contract):
    contract, _ = deploy_contract('SnapshotMock')
    return contract


timestamps = (0x00000001,
              0x00001000,
              0xff000000,
              0xffff0001)

values = (0x000000000000000000000000,
          0x000000000001000000000001,
          0xff0000000000000000000000,
          0xffff00000000000000000001)



@pytest.mark.parametrize('block_number, value', itertools.product(timestamps, values))
def test_snapshot(testerchain, snapshot, block_number, value):

    # Testing basic encoding and decoding of snapshots
    def encode(_time, _value):
        return snapshot.functions.encodeSnapshot(_time, _value).call()

    def decode(_snapshot):
        return snapshot.functions.decodeSnapshot(_snapshot).call()

    encoded_snapshot = encode(block_number, value)
    assert decode(encoded_snapshot) == [block_number, value]
    expected_encoded_snapshot_as_bytes = block_number.to_bytes(4, "big") + value.to_bytes(12, "big")
    assert Web3.toBytes(encoded_snapshot).rjust(16, b'\x00') == expected_encoded_snapshot_as_bytes

    # Testing adding new snapshots
    account = testerchain.etherbase_account

    data = [(block_number + i*10, value + i) for i in range(10)]
    for i, (block_i, value_i) in enumerate(data):
        tx = snapshot.functions.addSnapshot(block_i, value_i).transact({'from': account})
        receipt = testerchain.wait_for_receipt(tx)
        assert receipt['status'] == 1

        assert snapshot.functions.length().call() == i + 1
        assert snapshot.functions.history(i).call() == encode(block_i, value_i)
        assert snapshot.functions.lastSnapshot().call() == [block_i, value_i]

    # Testing getValueAt: simple case, when asking for the exact block number that was recorded
    for i, (block_i, value_i) in enumerate(data):
        assert snapshot.functions.getValueAt(block_i).call() == value_i
        assert snapshot.functions.history(i).call() == encode(block_i, value_i)

    # Testing getValueAt: general case, when retrieving block numbers in-between snapshots
    # Special cases are before first snapshot (where value should be 0) and after the last one
    prior_value = 0
    for block_i, value_i in data:
        assert snapshot.functions.getValueAt(block_i - 1).call() == prior_value
        prior_value = value_i

    last_block, last_value = snapshot.functions.lastSnapshot().call()
    assert snapshot.functions.getValueAt(last_block + 100).call() == last_value

    # Clear history for next test
    tx = snapshot.functions.deleteHistory().transact({'from': account})
    testerchain.wait_for_receipt(tx)
