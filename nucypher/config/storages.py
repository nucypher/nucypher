import os
from abc import abstractmethod, ABC
from logging import getLogger

import boto3 as boto3
from typing import Set, Callable

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class NodeStorage(ABC):

    _name = NotImplemented
    _TYPE_LABEL = 'storage_type'

    class NodeStorageError(Exception):
        pass

    class NoNodeMetadataFound(NodeStorageError):
        pass

    def __init__(self,
                 serializer: Callable,
                 deserializer: Callable,
                 federated_only: bool,  # TODO
                 ) -> None:

        self.log = getLogger(self.__class__.__name__)
        self.serializer = serializer
        self.deserializer = deserializer
        self.federated_only = federated_only

    def __getitem__(self, item):
        return self.get(checksum_address=item, federated_only=self.federated_only)

    def __setitem__(self, key, value):
        return self.save(node=value)

    def __delitem__(self, key):
        self.remove(checksum_address=key)

    def __iter__(self):
        return self.all(federated_only=self.federated_only)

    @abstractmethod
    def all(self, federated_only: bool) -> set:
        raise NotImplementedError

    @abstractmethod
    def get(self, checksum_address: str, federated_only: bool):
        raise NotImplementedError

    @abstractmethod
    def save(self, node):
        raise NotImplementedError

    @abstractmethod
    def remove(self, checksum_address: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def payload(self) -> str:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_payload(self, data: str, *args, **kwargs) -> 'NodeStorage':
        raise NotImplementedError

    @abstractmethod
    def initialize(self):
        raise NotImplementedError


class InMemoryNodeStorage(NodeStorage):

    _name = 'memory'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__known_nodes = dict()

    def all(self, federated_only: bool) -> set:
        return set(self.__known_nodes.values())

    def get(self, checksum_address: str, federated_only: bool):
        return self.__known_nodes[checksum_address]

    def save(self, node):
        self.__known_nodes[node.checksum_public_address] = node
        return True

    def remove(self, checksum_address: str) -> bool:
        del self.__known_nodes[checksum_address]
        return True

    def payload(self) -> dict:
        payload = {self._TYPE_LABEL: self._name}
        return payload

    @classmethod
    def from_payload(cls, payload: str, *args, **kwargs) -> 'InMemoryNodeStorage':
        if payload[cls._TYPE_LABEL] != cls._name:
            raise cls.NodeStorageError
        return cls(*args, **kwargs)

    def initialize(self) -> None:
        self.__known_nodes = dict()


class FileBasedNodeStorage(NodeStorage):

    _name = 'local'
    __FILENAME_TEMPLATE = '{}.node'
    __DEFAULT_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes', 'metadata')

    class NoNodeMetadataFound(FileNotFoundError, NodeStorage.NoNodeMetadataFound):
        pass

    def __init__(self,
                 known_metadata_dir: str = __DEFAULT_DIR,
                 *args, **kwargs
                 ) -> None:

        super().__init__(*args, **kwargs)
        self.log = getLogger(self.__class__.__name__)
        self.known_metadata_dir = known_metadata_dir

    def __generate_filepath(self, checksum_address: str) -> str:
        metadata_path = os.path.join(self.known_metadata_dir, self.__FILENAME_TEMPLATE.format(checksum_address))
        return metadata_path

    def __read(self, filepath: str, federated_only: bool):
        from nucypher.characters.lawful import Ursula
        with open(filepath, "r") as seed_file:
            seed_file.seek(0)
            node_bytes = self.deserializer(seed_file.read())
            node = Ursula.from_bytes(node_bytes, federated_only=federated_only)
        return node

    def __write(self, filepath: str, node):
        with open(filepath, "w") as f:
            f.write(self.serializer(node).hex())
        self.log.info("Wrote new node metadata to filesystem {}".format(filepath))
        return filepath

    def all(self, federated_only: bool) -> set:
        metadata_paths = sorted(os.listdir(self.known_metadata_dir), key=os.path.getctime)
        self.log.info("Found {} known node metadata files at {}".format(len(metadata_paths), self.known_metadata_dir))
        known_nodes = set()
        for metadata_path in metadata_paths:
            node = self.__read(filepath=metadata_path, federated_only=federated_only)   # TODO: 466
            known_nodes.add(node)
        return known_nodes

    def get(self, checksum_address: str, federated_only: bool):
        metadata_path = self.__generate_filepath(checksum_address=checksum_address)
        node = self.__read(filepath=metadata_path, federated_only=federated_only)   # TODO: 466
        return node

    def save(self, node):
        try:
            filepath = self.__generate_filepath(checksum_address=node.checksum_public_address)
        except AttributeError:
            raise AttributeError("{} does not have a rest_interface attached".format(self))  # TODO.. eh?
        self.__write(filepath=filepath, node=node)

    def remove(self, checksum_address: str):
        filepath = self.__generate_filepath(checksum_address=checksum_address)
        self.log.debug("Delted {} from the filesystem".format(checksum_address))
        return os.remove(filepath)

    def payload(self) -> str:
        payload = {
            'storage_type': self._name,
            'known_metadata_dir': self.known_metadata_dir
        }
        return payload

    @classmethod
    def from_payload(cls, payload: str, *args, **kwargs) -> 'FileBasedNodeStorage':
        storage_type = payload[cls._TYPE_LABEL]
        if not storage_type == cls._name:
            raise cls.NodeStorageError("Wrong storage type. got {}".format(storage_type))
        return cls(known_metadata_dir=payload['known_metadata_dir'], *args, **kwargs)

    def initialize(self):
        try:
            os.mkdir(self.known_metadata_dir, mode=0o755)  # known_metadata
        except FileExistsError:
            message = "There are pre-existing metadata files at {}".format(self.known_metadata_dir)
            raise self.NodeStorageError(message)
        except FileNotFoundError:
            raise self.NodeStorageError("There is no existing configuration at {}".format(self.known_metadata_dir))


class S3NodeStorage(NodeStorage):
    def __init__(self,
                 bucket_name: str,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        self.__bucket_name = bucket_name
        self.__s3client = boto3.client('s3')
        self.__s3resource = boto3.resource('s3')
        self.bucket = self.__s3resource.Bucket(bucket_name)

    def generate_presigned_url(self, checksum_address: str) -> str:
        payload = {'Bucket': self.__bucket_name, 'Key': checksum_address}
        url = self.__s3client.generate_presigned_url('get_object', payload)
        return url

    def all(self, federated_only: bool) -> set:
        raise NotImplementedError  # TODO

    def get(self, checksum_address: str, federated_only: bool):
        node_obj = self.bucket.Object(checksum_address)
        node = self.deserializer(node_obj)
        return node

    def save(self, node):
        self.__s3client.put_object(Bucket=self.__bucket_name,
                                   Key=node.checksum_public_address,
                                   Body=self.serializer(node))

    def remove(self, checksum_address: str) -> bool:
        _node_obj = self.get(checksum_address=checksum_address, federated_only=self.federated_only)
        return _node_obj()

    def payload(self) -> str:
        payload = {
            self._TYPE_LABEL: self._name,
            'bucket_name': self.__bucket_name
        }
        return payload

    @classmethod
    def from_payload(cls, payload: str, *args, **kwargs):
        return cls(bucket_name=payload['bucket_name'], *args, **kwargs)

    def initialize(self):
        return self.__s3client.create_bucket(Bucket=self.__bucket_name)

