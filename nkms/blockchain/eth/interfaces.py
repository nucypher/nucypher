import json


def __write_registrar_file(self, registrar_data: dict, registrar_filepath: str) -> None:
    """
    Writes the registrar data dict as JSON to the registrar file. If no
    file exists, it will create it and write the data. If a file does exist
    and contains JSON data, it will _overwrite_ everything in it.
    """
    with open(registrar_filepath, 'a+') as registrar_file:
        registrar_file.seek(0)
        registrar_file.write(json.dumps(registrar_data))
        registrar_file.truncate()


def __read_registrar_file(self, registrar_filepath: str) -> dict:
    """
    Reads the registrar file and parses the JSON and returns a dict.
    If the file is empty or the JSON is corrupt, it will return an empty
    dict.
    If you are modifying or updating the registrar file, you _must_ call
    this function first to get the current state to append to the dict or
    modify it because _write_registrar_file overwrites the file.
    """
    with open(registrar_filepath, 'r') as registrar_file:
        try:
            registrar_data = json.loads(registrar_file.read())
        except json.decoder.JSONDecodeError:
            registrar_data = dict()
    return registrar_data


class Registrar:
    """
    Records known contracts on the disk for future access and utility.

    WARNING: Unless you are developing the KMS/work at NuCypher, you most
    likely won't ever need to use this.
    """
    __DEFAULT_REGISTRAR_FILEPATH = None # TODO
    __DEFAULT_CHAIN_NAME = 'tester'

    class NoKnownContract(KeyError):
        pass

    def __init__(self, chain_name: str=None, registrar_filepath: str=None):
        self._chain_name = chain_name or self.__DEFAULT_CHAIN_NAME
        self.__registrar_filepath = registrar_filepath or self.__DEFAULT_REGISTRAR_FILEPATH

    @classmethod
    def get_chains(cls, registrar_filepath: str=None) -> dict:
        """
        Returns a dict of Registrar objects where the key is the chain name and
        the value is the Registrar object for that chain.
        Optionally, accepts a registrar filepath.
        """
        filepath = registrar_filepath or self.__DEFAULT_REGISTRAR_FILEPATH
        instance = cls(registrar_filepath=filepath)

        registrar_data = _read_registrar_file(filepath)
        chain_names = registrar_data.keys()

        chains = dict()
        for chain_name in chain_names:
            chains[chain_name] = cls(chain_name=chain_name,
                                     registrar_filepath=filepath)
        return chains

    def enroll(self, contract_name: str, contract_address: str, contract_abi: list) -> None:
        """
        Enrolls a contract to the chain registrar by writing the abi information
        to the filesystem as JSON. This can also be used to update the info
        under the specified `contract_name`.

        WARNING: Unless you are developing the KMS/work at NuCypher, you most
        likely won't ever need to use this.
        """
        enrolled_contract = {
                self._chain_name: {
                    contract_name: {
                        "addr": contract_address,
                        "abi": contract_abi
                }
            }
        }

        registrar_data = __read_registrar_file(self.__registrar_filepath)
        registrar_data.update(enrolled_contract)

        __write_registrar_file(registrar_data, self.__registrar_filepath)

    def get_chain_data(self) -> dict:
        """
        Returns all data from the current registrar chain as a dict.
        If no data exists for the current registrar chain, then it will raise
        KeyError.
        If you haven't specified the chain name, it's probably the tester chain.
        """
        registrar_data = __read_registrar_file(self.__registrar_filepath)
        try:
            chain_data = registrar_data[self._chain_name]
        except KeyError:
            raise KeyError("Data does not exist for chain '{}'".format(self._chain_name))
        return chain_data

    def get_contract_data(self, identifier: str=None) -> dict:
        """
        Returns contract data on the chain as a dict given an `identifier`.
        It first attempts to use identifier as a contract name. If no name is
        found, it will attempt to use identifier as an address.
        If no contract is found, it will raise NoKnownContract.
        """
        chain_data = self.get_chain_data()
        if identifier in chain_data:
            contract_data = chain_data[identifier]
            return contract_data
        else:
            for contract_name, contract_data in chain_data.items():
                if contract_data['addr'] == identifier:
                    return contract_data
        raise self.NoKnownContract(
            "Could not identify a contract name or address with {}".format(identifier)
        )
