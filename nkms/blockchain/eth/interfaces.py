import json


class Registrar:
    """
    Records known contracts on the disk for future access and utility.

    WARNING: Unless you are developing the KMS/work at NuCypher, you most
    likely won't ever need to use this.
    """
    __DEFAULT_REGISTRAR_FILEPATH = None # TODO

    class NoKnownContract(KeyError):
        pass

    def __init__(self, registrar_filepath: str=None):
        self.__registrar_filepath = registrar_filepath or self.__DEFAULT_REGISTRAR_FILEPATH

    def _write_registrar_file(self, registrar_data: dict) -> None:
        """
        Writes the registrar data dict as JSON to the registrar file. If no
        file exists, it will create it and write the data. If a file does exist
        and contains JSON data, it will _overwrite_ everything in it.
        """
        with open(self.__registrar_filepath, 'a+') as registrar_file:
            registrar_file.seek(0)
            registrar_file.write(json.dumps(registrar_data))
            registrar_file.truncate()

    def _read_registrar_file(self) -> dict:
        """
        Reads the registrar file and parses the JSON and returns a dict.
        If the file is empty or the JSON is corrupt, it will return an empty
        dict.
        If you are modifying or updating the registrar file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registrar_file overwrites the file.
        """
        with open(self.__registrar_filepath, 'r') as registrar_file:
            try:
                registrar_data = json.loads(registrar_file.read())
            except json.decoder.JSONDecodeError:
                registrar_data = dict()
        return registrar_data

    def enroll(self, contract_name: str, contract_address: str, contract_abi: list):
        """
        Enrolls a contract to the registrar by writing the abi information to
        the filesystem as JSON.

        WARNING: Unless you are developing the KMS/work at NuCypher, you most
        likely won't ever need to use this.
        """
        enrolled_contract = {
            contract_name: {
                "addr": contract_address,
                "abi": contract_abi
            }
        }

        registrar_data = self._read_registrar_file()
        registrar_data.update(enrolled_contract)

        self._write_registrar_file(registrar_data)
