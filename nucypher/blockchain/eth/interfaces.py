import binascii
import json
import os
import warnings
from pathlib import Path
from typing import Tuple, List

from constant_sorrow import constants
from eth_utils import to_canonical_address
from eth_keys.datatypes import PublicKey, Signature
from web3.providers.eth_tester.main import EthereumTesterProvider
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract

from nucypher.blockchain.eth.sol.compile import SolidityCompiler

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class EthereumContractRegistrar:
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing NuCypher, you most
    likely won't ever need to use this.
    """
    __default_registrar_path = os.path.join(_DEFAULT_CONFIGURATION_DIR, 'registrar.json')
    __default_chain_name = 'tester'

    class UnknownContract(KeyError):
        pass

    class UnknownChain(KeyError):
        pass

    def __init__(self, chain_name: str=None, registrar_filepath: str=None):
        self._chain_name = chain_name or self.__default_chain_name
        self.__registrar_filepath = registrar_filepath or self.__default_registrar_path

    def __write(self, registrar_data: dict) -> None:
        """
        Writes the registrar data dict as JSON to the registrar file. If no
        file exists, it will create it and write the data. If a file does exist
        and contains JSON data, it will _overwrite_ everything in it.
        """
        with open(self.__registrar_filepath, 'w+') as registrar_file:
            registrar_file.seek(0)
            registrar_file.write(json.dumps(registrar_data))
            registrar_file.truncate()

    def __read(self) -> dict:
        """
        Reads the registrar file and parses the JSON and returns a dict.
        If the file is empty or the JSON is corrupt, it will return an empty
        dict.
        If you are modifying or updating the registrar file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registrar_file overwrites the file.
        """
        try:
            with open(self.__registrar_filepath, 'r') as registrar_file:
                registrar_file.seek(0)
                registrar_data = json.loads(registrar_file.read())
                if self._chain_name not in registrar_data:
                    registrar_data[self._chain_name] = dict()
        except (json.decoder.JSONDecodeError, FileNotFoundError):
            registrar_data = {self._chain_name: dict()}
        return registrar_data

    @classmethod
    def get_registrars(cls, registrar_filepath: str=None) -> dict:
        """
        Returns a dict of Registrar objects where the key is the chain name and
        the value is the Registrar object for that chain.
        Optionally, accepts a registrar filepath.
        """
        filepath = registrar_filepath or cls.__default_registrar_path
        instance = cls(registrar_filepath=filepath)

        registrar_data = instance.__read()
        chain_names = registrar_data.keys()

        chains = dict()
        for chain_name in chain_names:
            chains[chain_name] = cls(chain_name=chain_name, registrar_filepath=filepath)
        return chains

    def enroll(self, contract_name: str, contract_addr: str, contract_abi: list) -> None:
        """
        Enrolls a contract to the chain registrar by writing the abi information
        to the filesystem as JSON. This can also be used to update the info
        under the specified `contract_name`.

        Note: Unless you are developing NuCypher, you most likely won't ever need to use this.
        """
        contract_data = {
            contract_addr: {
                "name": contract_name,
                "abi": contract_abi,
                "addr": contract_addr
            }
        }

        registrar_data = self.__read()

        reg_contract_data = registrar_data.get(self._chain_name, dict())
        reg_contract_data.update(contract_data)

        registrar_data[self._chain_name].update(reg_contract_data)
        self.__write(registrar_data)

    def dump_chain(self) -> dict:
        """
        Returns all data from the current registrar chain as a dict.
        If no data exists for the current registrar chain, then it will raise
        KeyError.
        If you haven't specified the chain name, it's probably the tester chain.
        """

        registrar_data = self.__read()
        try:
            chain_data = registrar_data[self._chain_name]
        except KeyError:
            raise self.UnknownChain("Data does not exist for chain '{}'".format(self._chain_name))
        return chain_data

    def lookup_contract(self, contract_name: str) -> List[dict]:
        """
        Search the registarar for all contracts that match a given
        contract name and return them in a list.
        """

        chain_data = self.dump_chain()

        contracts = list()
        for _address, contract_data in chain_data.items():
            if contract_data['name'] == contract_name:
                contracts.append(contract_data)

        if len(contracts) > 0:
            return contracts
        else:
            m = 'Contract name or address: {}, for chain: {} was not found in the registrar. ' \
                'Ensure that the contract is deployed, registered.'.format(contract_name, self._chain_name)

            raise self.UnknownContract(m)

    def dump_contract(self, address: str=None) -> dict:
        """
        Returns contracts in a list that match the provided identifier on a
        given chain. It first attempts to use identifier as a contract name.
        If no name is found, it will attempt to use identifier as an address.
        If no contract is found, it will raise NoKnownContract.
        """

        chain_data = self.dump_chain()
        if address in chain_data:
            return chain_data[address]

        # Fallback, search by name
        for contract_identifier, contract_data in chain_data.items():
            if contract_data['name'] == address:
                return contract_data
        else:
            raise self.UnknownContract('No known contract with address: {}'.format(address))


class ControlCircumflex:
    """
    Interacts with a solidity compiler and a registrar in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """
    __fallabck_providers = (IPCProvider(ipc_path='/tmp/geth.ipc'), )  # user-managed geth over IPC default
    __default_timeout = 10  # seconds
    __default_network = 'tester'
    __default_transaction_gas_limit = 500000  # TODO: determine sensible limit and validate transactions

    class UnknownContract(Exception):
        pass

    class InterfaceError(Exception):
        pass

    def __init__(self, network_name: str=None, endpoint_uri: str=None,
                 websocket=False, ipc_path=None, timeout=None, providers: list=None,
                 registrar: EthereumContractRegistrar=None, compiler: SolidityCompiler=None):

        """
        A blockchain "network inerface"; The circumflex wraps entirely around the bounds of
        contract operations including compilation, deployment, and execution.


         Solidity Files -- SolidityCompiler ---                  --- HTTPProvider --
                                               |                |                   |
                                               |                |                    -- External EVM (geth, etc.)
                                                                                    |
                                               *ControlCircumflex* -- IPCProvider --

                                               |      |         |
                                               |      |         |
         Registrar File -- ContractRegistrar --       |          ---- TestProvider -- EthereumTester
                                                      |
                                                      |                                  |
                                                      |
                                                                                       Pyevm (development chain)
                                                 Blockchain

                                                      |

                                                    Agent ... (Contract API)

                                                      |

                                                Character / Actor


        The circumflex is the junction of the solidity compiler, a contract registrar, and a collection of
        web3 network __providers as a means of interfacing with the ethereum blockchain to execute
        or deploy contract code on the network.


        Compiler and Registrar Usage
        -----------------------------

        Contracts are freshly re-compiled if an instance of SolidityCompiler is passed; otherwise,
        The registrar will read contract data saved to disk that is be used to retrieve contact address and op-codes.
        Optionally, A registrar instance can be passed instead.


        Provider Usage
        ---------------
        https: // github.com / ethereum / eth - tester     # available-backends


        * HTTP Provider - supply endpiont_uri
        * Websocket Provider - supply endpoint uri and websocket=True
        * IPC Provider - supply IPC path
        * Custom Provider - supply an iterable of web3.py provider instances

        """

        self.__network = network_name if network_name is not None else self.__default_network
        self.timeout = timeout if timeout is not None else self.__default_timeout

        #
        # Providers
        #

        # If custom __providers are not injected...
        self._providers = list() if providers is None else providers
        if providers is None:
            # Mutates self._providers
            self.add_provider(endpoint_uri=endpoint_uri, websocket=websocket,
                              ipc_path=ipc_path, timeout=timeout)

        web3_instance = Web3(providers=self._providers)  # Instantiate Web3 object with provider
        self.w3 = web3_instance                           # capture web3

        # if a SolidityCompiler class instance was passed, compile from solidity source code
        recompile = True if compiler is not None else False
        self.__recompile = recompile
        self.__sol_compiler = compiler

        # Setup the registrar and base contract factory cache
        registrar = registrar if registrar is not None else EthereumContractRegistrar(chain_name=network)
        self._registrar = registrar

        # Execute the compilation if we're recompiling, otherwise read compiled contract data from the registrar
        interfaces = self.__sol_compiler.compile() if self.__recompile is True else self._registrar.dump_chain()
        self.__raw_contract_cache = interfaces

    @property
    def network(self) -> str:
        return self.__network

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__providers.html#examples-using-automated-detection
        """
        return self.w3.isConnected()

    @property
    def version(self) -> str:
        """Return node version information"""
        return self.w3.version.node           # type of connected node

    def add_provider(self, provider=None, endpoint_uri: str=None, websocket=False, ipc_path=None, timeout=None) -> None:

        if provider is None:
            # Validate parameters
            if websocket and not endpoint_uri:
                if ipc_path is not None:
                    raise self.InterfaceError("Use either HTTP/Websocket or IPC params, not both.")
                raise self.InterfaceError('Must pass endpoint_uri when using websocket __providers.')

            if ipc_path is not None:
                if endpoint_uri or websocket:
                    raise self.InterfaceError("Use either HTTP/Websocket or IPC params, not both.")

            # HTTP / Websocket Provider
            if endpoint_uri is not None:
                if websocket is True:
                    provider = WebsocketProvider(endpoint_uri)
                else:
                    provider = HTTPProvider(endpoint_uri)

            # IPC Provider
            elif ipc_path:
                provider = IPCProvider(ipc_path=ipc_path, testnet=False, timeout=timeout)
            else:
                raise self.InterfaceError("Invalid interface parameters. Pass endpoint_uri or ipc_path")

        self._providers.append(provider)

    def get_contract_factory(self, contract_name) -> Contract:
        """Retrieve compiled interface data from the cache and return web3 contract"""
        try:
            interface = self.__raw_contract_cache[contract_name]
        except KeyError:
            raise self.UnknownContract('{} is not a compiled contract.'.format(contract_name))

        contract = self.w3.eth.contract(abi=interface['abi'],
                                        bytecode=interface['bin'],
                                        ContractFactoryClass=Contract)

        return contract

    def get_contract_address(self, contract_name: str) -> List[str]:
        """Retrieve all known addresses for this contract"""
        contracts = self._registrar.lookup_contract(contract_name=contract_name)
        addresses = [c['addr'] for c in contracts]
        return addresses

    def get_contract(self, address: str) -> Contract:
        """Instantiate a deployed contract from registrar data"""
        contract_data = self._registrar.dump_contract(address=address)
        contract = self.w3.eth.contract(abi=contract_data['abi'], address=contract_data['addr'])
        return contract


class DeployerCircumflex(ControlCircumflex):

    def __init__(self, deployer_address: str=None, *args, **kwargs):

        # Depends on web3 instance
        super().__init__(*args, **kwargs)
        self.__deployer_address = deployer_address if deployer_address is not None else constants.NO_DEPLOYER_CONFIGURED

    @property
    def deployer_address(self):
        return self.__deployer_address

    @deployer_address.setter
    def deployer_address(self, ether_address: str) -> None:
        if self.deployer_address is not constants.NO_DEPLOYER_CONFIGURED:
            raise RuntimeError("{} already has a deployer address set.".format(self.__class__.__name__))
        self.__deployer_address = ether_address

    def deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[Contract, str]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """

        #
        # Build the deployment tx #
        #
        contract_factory = self.get_contract_factory(contract_name=contract_name)
        deploy_transaction = {'from': self.deployer_address, 'gasPrice': self.w3.eth.gasPrice}  # TODO: price?
        deploy_bytecode = contract_factory.constructor(*args, **kwargs).buildTransaction(deploy_transaction)

        # TODO: Logging
        contract_sizes = dict()
        if len(deploy_bytecode['data']) > 1000:
            contract_sizes[contract_name] = str(len(deploy_bytecode['data']))

        #
        # Transmit the deployment tx #
        #
        txhash = contract_factory.constructor(*args, **kwargs).transact(transaction=deploy_transaction)

        # Wait for receipt
        receipt = self.w3.eth.waitForTransactionReceipt(txhash)
        address = receipt['contractAddress']

        #
        # Instantiate & enroll contract
        #
        contract = contract_factory(address=address)
        self._registrar.enroll(contract_name=contract_name,
                               contract_addr=contract.address,
                               contract_abi=contract_factory.abi)

        return contract, txhash

    def call_backend_sign(self, account: str, message: bytes) -> str:
        """
        Calls the appropriate signing function for the specified account on the
        backend. If the backend is based on eth-tester, then it uses the
        eth-tester signing interface to do so.
        """
        provider = self._providers[0]
        if isinstance(provider, EthereumTesterProvider):
            address = to_canonical_address(account)
            sig_key = provider.ethereum_tester.backend._key_lookup[address]
            signed_message = sig_key.sign_msg(message)
            return signed_message.to_hex()
        else:
            return self.w3.eth.sign(account, data=message) # Technically deprecated...

    def call_backend_verify(self, pubkey: PublicKey, signature: Signature, msg_hash: bytes):
        """
        Verifies a hex string signature and message hash are from the provided
        public key.
        """
        is_valid_sig = signature.verify_msg_hash(msg_hash, pubkey)
        sig_pubkey = signature.recover_public_key_from_msg_hash(msg_hash)

        return is_valid_sig and (sig_pubkey == pubkey)
