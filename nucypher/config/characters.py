import os

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.node import NodeConfiguration


class UrsulaConfiguration(NodeConfiguration):

    # REST
    DEFAULT_TLS_CERTIFICATE_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'ursula.pem')
    DEFAULT_REST_HOST = 'localhost'
    DEFAULT_REST_PORT = 9151
    DEFAULT_SIMULATION_PORT = 8151

    # Database
    DEFAULT_DB_NAME = "ursula.{port}.db".format(port=DEFAULT_REST_PORT)

    # Blockchain
    DEFAULT_REGISTRY_FILEPATH = os.path.join(DEFAULT_CONFIG_ROOT, 'simulation_registry.json')

    def ___init__(self,
                  rest_host: str = DEFAULT_REST_HOST,
                  rest_port: int = DEFAULT_REST_PORT,
                  tls_certificate_filepath: str = DEFAULT_TLS_CERTIFICATE_FILEPATH,
                  db_name: str = DEFAULT_DB_NAME,
                  registry_filepath: str = DEFAULT_REGISTRY_FILEPATH):

        # REST
        self.tls_certificate_filepath = tls_certificate_filepath
        self.rest_host = rest_host
        self.rest_port = rest_port

        # Database
        self.db_name = db_name

        # Blockchain
        self.registry_filepath = registry_filepath

        super().__init__()

    @classmethod
    def from_config_file(cls, filepath=None) -> 'UrsulaConfiguration':
        from nucypher.config.parsers import parse_ursula_config

        filepath = filepath if filepath is None else cls.DEFAULT_CONFIG_FILE_LOCATION
        payload = parse_ursula_config(filepath=filepath)
        instance = cls(**payload)
        return instance


class AliceConfiguration(NodeConfiguration):

    @classmethod
    def from_config_file(cls, filepath=None) -> 'AliceConfiguration':
        from nucypher.config.parsers import parse_alice_config

        filepath = filepath if filepath is None else cls.DEFAULT_CONFIG_FILE_LOCATION
        payload = parse_alice_config(filepath=filepath)
        instance = cls(**payload)
        return instance


# TODO:
# class BobConfiguration(NodeConfiguration):
#
#     @classmethod
#     def from_config_file(cls, filepath=None) -> 'BobConfiguration':
#         from nucypher.config.parsers import parse_bob_config
#
#         filepath = filepath if filepath is None else cls.DEFAULT_INI_FILEPATH
#         payload = parse_bob_config(filepath=filepath)
#         instance = cls(**payload)
#         return instance
