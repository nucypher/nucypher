from nucypher.config.parsers import parse_blockchain_config


class BlockchainConfiguration:

    def __init__(self):
        pass

    @classmethod
    def from_config_file(cls, filepath: str):
        parse_blockchain_config(filepath=filepath)
