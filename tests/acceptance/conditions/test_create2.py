import os

import pytest

from nucypher.policy.conditions.lingo import VariableOperation


@pytest.fixture(scope="module")
def create2_factory(project, deployer_account):
    """Deploy the Create2Factory contract for testing."""
    return deployer_account.deploy(project.Create2Factory)


def test_create2_matches_contract_with_different_deployers(
    create2_factory, get_random_checksum_address
):
    """
    Test create2 computation with various deployer addresses.
    """
    salt = os.urandom(32)
    bytecode_hash = os.urandom(32)

    # Test with multiple different deployer addresses
    for _ in range(5):
        deployer_address = get_random_checksum_address()

        operations = [
            VariableOperation(
                operation="create2",
                value={
                    "deployerAddress": deployer_address,
                    "bytecodeHash": "0x" + bytecode_hash.hex(),
                },
            ),
        ]
        local_result = VariableOperation.evaluate_operations(operations, salt)

        contract_result = create2_factory.computeAddress(
            salt, bytecode_hash, deployer_address
        )

        assert local_result == contract_result


def test_create2_matches_contract_multiple_random_inputs(create2_factory):
    """
    Test create2 computation with multiple sets of random inputs
    to ensure consistent matching with the contract.
    """
    deployer_address = create2_factory.address

    for _ in range(10):
        salt = os.urandom(32)
        bytecode_hash = os.urandom(32)

        operations = [
            VariableOperation(
                operation="create2",
                value={
                    "deployerAddress": deployer_address,
                    "bytecodeHash": "0x" + bytecode_hash.hex(),
                },
            ),
        ]
        local_result = VariableOperation.evaluate_operations(operations, salt)

        contract_result = create2_factory.computeAddress(
            salt, bytecode_hash, deployer_address
        )

        assert local_result == contract_result
