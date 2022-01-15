"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import json
import os
import random

import pytest
from eth_utils import to_canonical_address
from web3 import EthereumTesterProvider, Web3

from nucypher.blockchain.eth.aragon import CallScriptCodec, DAORegistry
from nucypher.blockchain.eth.constants import DAO_INSTANCES_CONTRACT_TYPE
from nucypher.blockchain.eth.networks import NetworksInventory


#
# CallscriptCodec tests
#

@pytest.fixture()
def mock_web3_contract():
    w3 = Web3(EthereumTesterProvider())

    foo_abi = dict(constant=False,
                   inputs=[],
                   name="foo",
                   outputs=[],
                   payable=False,
                   stateMutability="pure",
                   type="function")

    bar_abi = dict(constant=False,
                   inputs=[dict(name="", type="address")],
                   name="bar",
                   outputs=[],
                   payable=False,
                   stateMutability="pure",
                   type="function")

    abi = [foo_abi, bar_abi]
    contract = w3.eth.contract(abi=abi)
    return contract


def test_callscriptcodec():
    assert CallScriptCodec.CALLSCRIPT_ID == bytes.fromhex("00000001")


def test_callscript_encoding_empty():
    actions = tuple()

    callscript_data = CallScriptCodec.encode_actions(actions)
    expected_callscript = CallScriptCodec.CALLSCRIPT_ID
    assert expected_callscript == callscript_data


@pytest.mark.parametrize('data_length', range(0, 100, 5))
def test_callscript_encoding_one_action(get_random_checksum_address, data_length, mock_web3_contract):
    # Action is a byte string
    target = get_random_checksum_address()
    data = os.urandom(data_length)
    actions = [(target, data)]

    callscript_data = CallScriptCodec.encode_actions(actions)
    expected_callscript = b''.join((CallScriptCodec.CALLSCRIPT_ID,
                                    to_canonical_address(target),
                                    data_length.to_bytes(4, 'big'),
                                    data))
    assert expected_callscript == callscript_data

    # Action is a hex string
    data = Web3.toHex(data)
    actions = [(target, data)]
    callscript_data = CallScriptCodec.encode_actions(actions)
    assert expected_callscript == callscript_data

    # Action is a ContractFunction
    function_call = mock_web3_contract.functions.foo()
    actions = [(target, function_call)]
    encoded_foo = Web3.toBytes(hexstr=mock_web3_contract.encodeABI(fn_name="foo"))

    expected_callscript = b''.join((CallScriptCodec.CALLSCRIPT_ID,
                                    to_canonical_address(target),
                                    len(encoded_foo).to_bytes(4, 'big'),
                                    encoded_foo))
    callscript_data = CallScriptCodec.encode_actions(actions)
    assert expected_callscript == callscript_data


@pytest.mark.parametrize('number_of_actions', range(1, 5))
def test_callscript_encode_multiple_actions(get_random_checksum_address, number_of_actions):
    actions = [(get_random_checksum_address(), os.urandom(random.randrange(100))) for _ in range(number_of_actions)]

    callscript_chunks = [CallScriptCodec.CALLSCRIPT_ID]
    for target, data in actions:
        callscript_chunks.extend([to_canonical_address(target), len(data).to_bytes(4, 'big'), data])
    expected_callscript = b''.join(callscript_chunks)

    callscript_data = CallScriptCodec.encode_actions(actions)
    assert expected_callscript == callscript_data


#
# DAORegistry tests
#

@pytest.fixture(scope='module')
def create_mock_dao_registry():
    def _create_mock_dao_registry(path, registry_data):
        filepath = path / DAORegistry._REGISTRY_FILENAME
        path.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as file:
            json.dump(registry_data, file)

        return filepath
    return _create_mock_dao_registry


def test_dao_registry(tmp_path, create_mock_dao_registry, get_random_checksum_address, mocker):
    NetworksInventory.validate_network_name = lambda _: None
    network = "bananas"
    mocker.patch("nucypher.blockchain.eth.aragon.DAORegistry.get_filepath",
                 return_value=tmp_path / network / DAORegistry._REGISTRY_FILENAME)

    # Let's create some mock registry data
    registry_data = dict()
    for name, app_name in DAO_INSTANCES_CONTRACT_TYPE.items():
        registry_data[name] = dict(app_name=app_name, address=get_random_checksum_address())

    # Testing normal usage of DAORegistry
    dao_registry_filepath = create_mock_dao_registry(path=tmp_path / network, registry_data=registry_data)
    dao_registry = DAORegistry(network=network)
    assert dao_registry_filepath == dao_registry.filepath
    for name, app_name in DAO_INSTANCES_CONTRACT_TYPE.items():
        assert app_name == dao_registry.get_app_name_of(name)
        assert registry_data[name]['address'] == dao_registry.get_address_of(name)

    # Testing expected exceptions
    with pytest.raises(ValueError, match="🍌 is not a recognized instance of NuCypherDAO."):
        _ = dao_registry.get_address_of(instance_name="🍌")

    unknown_address = get_random_checksum_address()
    with pytest.raises(DAORegistry.InstanceNotInRegistry,
                       match=f"No instance found in the NuCypherDAO registry with address {unknown_address}"):
        _ = dao_registry.get_instance_name_by_address(unknown_address)

    # Finding an unknown DAO instance in the registry file should raise an exception
    new_instance = "AgentProvocateur"
    registry_data[new_instance] = dict(app_name="Foo", address=get_random_checksum_address())
    _ = create_mock_dao_registry(path=tmp_path / network, registry_data=registry_data)
    with pytest.raises(ValueError, match="AgentProvocateur is not a recognized instance of NuCypherDAO."):
        _ = DAORegistry(network=network)
