import os
from glob import glob
from os.path import abspath

from constant_sorrow import constants
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.x509 import Certificate

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.config.constants import DEFAULT_CONFIG_FILE_LOCATION
from nucypher.config.node import NodeConfiguration
from nucypher.crypto.powers import CryptoPower


class UrsulaConfiguration(NodeConfiguration):

    DEFAULT_TLS_CURVE = ec.SECP384R1
    DEFAULT_REST_HOST = 'localhost'
    DEFAULT_REST_PORT = 9151

    def __init__(self,
                 rest_host: str = DEFAULT_REST_HOST,
                 rest_port: int = DEFAULT_REST_PORT,

                 # TLS
                 tls_curve: EllipticCurve = DEFAULT_TLS_CURVE,
                 tls_private_key=None,
                 certificate: bytes = None,
                 certificate_filepath: str = None,

                 # Ursula
                 db_name: str = None,
                 db_filepath: str = None,
                 interface_signature=None,
                 crypto_power=None,

                 # Blockchain
                 miner_agent: EthereumContractAgent = None,
                 checksum_address: str = None,
                 registry_filepath: str = None,

                 *args, **kwargs
                 ) -> None:

        # REST
        self.rest_host = rest_host
        self.rest_port = rest_port
        self.db_name = db_name or "ursula.{port}.db".format(port=self.rest_port)
        self.db_filepath = db_filepath or constants.UNINITIALIZED_CONFIGURATION

        #
        # TLS
        #
        self.tls_curve = tls_curve
        self.tls_private_key = tls_private_key
        self.certificate: bytes = certificate

        # if certificate_filepath is None:
        #     certificate_filepath = certificate_filepath or os.path.join(self.known_certificates_dir, 'ursula.pem')
        self.certificate_filepath = certificate_filepath

        # Ursula
        self.interface_signature = interface_signature
        self.crypto_power = crypto_power

        #
        # Blockchain
        #
        self.miner_agent = miner_agent
        self.checksum_address = checksum_address
        self.registry_filepath = registry_filepath or constants.UNINITIALIZED_CONFIGURATION

        super().__init__(*args, **kwargs)

    @classmethod
    def from_configuration_file(cls, filepath=None, **overrides) -> 'UrsulaConfiguration':
        from nucypher.config.parsers import parse_ursula_config
        filepath = filepath if filepath is None else DEFAULT_CONFIG_FILE_LOCATION
        payload = parse_ursula_config(filepath=filepath)
        instance = cls(**{**payload, **overrides})
        return instance

    def generate_runtime_filepaths(self):
        super().generate_runtime_filepaths()
        self.db_filepath = os.path.join(self.config_root, self.db_name)
        self.registry_filepath = os.path.join(self.config_root, 'contract_registry.json')

    @property
    def payload(self) -> dict:

        ursula_payload = dict(

                 # REST
                 rest_host=self.rest_host,
                 rest_port=self.rest_port,
                 db_name=self.db_name,
                 db_filepath=self.db_filepath,

                 # TLS
                 tls_curve=self.tls_curve,
                 tls_private_key=self.tls_private_key,
                 certificate=self.certificate,
                 # certificate_filepath=self.certificate_filepath,  # TODO

                 # Ursula
                 interface_signature=self.interface_signature,
                 crypto_power=self.crypto_power,

                 # Blockchain
                 miner_agent=self.miner_agent,
                 checksum_address=self.checksum_address,
                 registry_filepath=self.registry_filepath
        )

        base_payload = super().payload
        ursula_payload.update(base_payload)
        return ursula_payload

    def produce(self, **overrides):
        merged_parameters = {**self.payload, **overrides}
        from nucypher.characters.lawful import Ursula
        ursula = Ursula(**merged_parameters)

        if self.temp:
            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)
            ursula.datastore_threadpool = MockDatastoreThreadPool()

        return ursula

    def load_known_nodes(self, known_metadata_dir=None) -> None:

        if known_metadata_dir is None:
            known_metadata_dir = self.known_metadata_dir
        glob_pattern = os.path.join(known_metadata_dir, 'node-*.data')
        metadata_paths = sorted(glob(glob_pattern), key=os.path.getctime)

        for metadata_path in metadata_paths:
            from nucypher.characters.lawful import Ursula
            node = Ursula.from_metadata_file(filepath=abspath(metadata_path))
            self.known_nodes.add(node)


class AliceConfiguration(NodeConfiguration):

    def __init__(self,
                 policy_agent=None,
                 *args, **kwargs
                 ) -> None:
        super().__init__(*args, **kwargs)
        self.policy_agent = policy_agent

    @property
    def payload(self) -> dict:

        alice_payload = dict(
            policy_agent=self.policy_agent
        )

        base_payload = super().payload
        alice_payload.update(base_payload)
        return alice_payload

    def produce(self, **overrides):
        merged_parameters = {**self.payload, **overrides}
        from nucypher.characters.lawful import Alice
        alice = Alice(**merged_parameters)
        return alice

    @classmethod
    def from_configuration_file(cls, filepath=None) -> 'AliceConfiguration':
        from nucypher.config.parsers import parse_alice_config
        filepath = filepath if filepath is None else DEFAULT_CONFIG_FILE_LOCATION
        payload = parse_alice_config(filepath=filepath)
        instance = cls(**payload)
        return instance
