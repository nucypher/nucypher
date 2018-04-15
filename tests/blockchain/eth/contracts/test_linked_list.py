"""
tests taken from
https://github.com/Majoolr/ethereum-libraries/blob/master/LinkedListLib/truffle/test/TestLinkedListLib.sol
"""

NULL = '0x0000000000000000000000000000000000000000'
HEAD = NULL
PREV = False
NEXT = True


def test_linked_list(web3, chain):
    address1 = web3.eth.accounts[0]
    address2 = web3.eth.accounts[1]
    address3 = web3.eth.accounts[2]
    address4 = web3.eth.accounts[3]

    # Deploy test contract
    instance, _ = chain.provider.get_or_deploy_contract('LinkedListMock')

    # Check that list is empty
    assert not instance.call().exists()
    assert instance.call().sizeOf() == 0
    # assert instance.call().seek(HEAD, address2, NEXT) == NULL

    # Insert new value
    tx = instance.transact().insert(HEAD, address2, NEXT)
    chain.wait_for_receipt(tx)
    assert instance.call().exists()
    assert instance.call().sizeOf() == 1
    assert instance.call().valueExists(address2)

    # Insert more values
    tx = instance.transact().insert(address2, address1, PREV)
    chain.wait_for_receipt(tx)
    tx = instance.transact().insert(address2, address3, NEXT)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 3

    # Try to remove non-existent value
    assert instance.call().remove(address4) == NULL

    # Remove middle value
    assert instance.call().remove(address2) == address2
    tx = instance.transact().remove(address2)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 2

    # Check node
    node = instance.call().getLinks(address1)
    assert node[0] == HEAD
    assert node[1].lower() == address3.lower()

    # Remove another value
    assert instance.call().remove(address3) == address3
    tx = instance.transact().remove(address3)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 1

    # Check node
    node = instance.call().getLinks(address1)
    assert node[0] == HEAD
    assert node[1] == HEAD

    # Remove last value
    assert instance.call().remove(address1).lower() == address1.lower()
    tx = instance.transact().remove(address1)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 0

    # Check head node
    node = instance.call().getLinks(HEAD)
    assert node[0] == HEAD
    assert node[1] == HEAD

    # Push values
    tx = instance.transact().push(address2, NEXT)
    chain.wait_for_receipt(tx)
    tx = instance.transact().push(address3, PREV)
    chain.wait_for_receipt(tx)
    tx = instance.transact().push(address1, NEXT)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 3

    # Check nodes
    node = instance.call().getLinks(address3)
    assert node[0].lower() == address2.lower()
    assert node[1] == HEAD
    node = instance.call().getLinks(address1)
    assert node[0] == HEAD
    assert node[1].lower() == address2.lower()

    # Pop values
    assert instance.call().pop(NEXT).lower() == address1.lower()
    assert instance.call().pop(PREV).lower() == address3.lower()
    tx = instance.transact().pop(NEXT)
    chain.wait_for_receipt(tx)
    tx = instance.transact().pop(PREV)
    chain.wait_for_receipt(tx)
    assert instance.call().sizeOf() == 1

    # Check last node
    node = instance.call().getLinks(address2)
    assert node[0] == HEAD
    assert node[1] == HEAD
