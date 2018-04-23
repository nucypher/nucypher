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
    instance, _ = chain.provider.deploy_contract('LinkedListMock')

    # Check that list is empty
    assert not instance.functions.exists().call()
    assert instance.functions.sizeOf().call() == 0
    # assert instance.functions.seek(HEAD, address2, NEXT).call() == NULL

    # Insert new value
    tx =  instance.functions.insert(HEAD, address2, NEXT).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.exists().call()
    assert instance.functions.sizeOf().call() == 1
    assert instance.functions.valueExists(address2).call()

    # Insert more values
    tx =  instance.functions.insert(address2, address1, PREV).transact({'from': address1})
    chain.wait_for_receipt(tx)
    tx =  instance.functions.insert(address2, address3, NEXT).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 3

    # Try to remove non-existent value
    assert instance.functions.remove(address4).call() == NULL

    # Remove middle value
    assert instance.functions.remove(address2).call() == address2
    tx =  instance.functions.remove(address2).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 2

    # Check node
    node = instance.functions.getLinks(address1).call()
    assert node[0] == HEAD
    assert node[1] == address3

    # Remove another value
    assert instance.functions.remove(address3).call() == address3
    tx =  instance.functions.remove(address3).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 1

    # Check node
    node = instance.functions.getLinks(address1).call()
    assert node[0] == HEAD
    assert node[1] == HEAD

    # Remove last value
    assert instance.functions.remove(address1).call() == address1
    tx =  instance.functions.remove(address1).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 0

    # Check head node
    node = instance.functions.getLinks(HEAD).call()
    assert node[0] == HEAD
    assert node[1] == HEAD

    # Push values
    tx =  instance.functions.push(address2, NEXT).transact({'from': address1})
    chain.wait_for_receipt(tx)
    tx =  instance.functions.push(address3, PREV).transact({'from': address1})
    chain.wait_for_receipt(tx)
    tx =  instance.functions.push(address1, NEXT).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 3

    # Check nodes
    node = instance.functions.getLinks(address3).call()
    assert node[0] == address2
    assert node[1] == HEAD
    node = instance.functions.getLinks(address1).call()
    assert node[0] == HEAD
    assert node[1] == address2

    # Pop values
    assert instance.functions.pop(NEXT).call() == address1
    assert instance.functions.pop(PREV).call() == address3
    tx =  instance.functions.pop(NEXT).transact({'from': address1})
    chain.wait_for_receipt(tx)
    tx =  instance.functions.pop(PREV).transact({'from': address1})
    chain.wait_for_receipt(tx)
    assert instance.functions.sizeOf().call() == 1

    # Check last node
    node = instance.functions.getLinks(address2).call()
    assert node[0] == HEAD
    assert node[1] == HEAD
