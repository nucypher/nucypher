"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import binascii
import os
import tempfile
from abc import abstractmethod, ABC
from twisted.logger import Logger

import boto3 as boto3
import shutil
from botocore.errorfactory import ClientError
from constant_sorrow import constants
from typing import Callable

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class NodeStorage(ABC):

    _name = NotImplemented
    _TYPE_LABEL = 'storage_type'
    NODE_SERIALIZER = binascii.hexlify
    NODE_DESERIALIZER = binascii.unhexlify

    class NodeStorageError(Exception):
        pass

    class UnknownNode(NodeStorageError):
        pass

    def __init__(self,
                 character_class,
                 federated_only: bool,  # TODO# 466
                 serializer: Callable = NODE_SERIALIZER,
                 deserializer: Callable = NODE_DESERIALIZER,
                 ) -> None:

        self.log = Logger(self.__class__.__name__)
        self.serializer = serializer
        self.deserializer = deserializer
        self.federated_only = federated_only
        self.character_class = character_class

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
        """Return s set of all stored nodes"""
        raise NotImplementedError

    @abstractmethod
    def get(self, checksum_address: str, federated_only: bool):
        """Retrieve a single stored node"""
        raise NotImplementedError

    @abstractmethod
    def save(self, node):
        """Save a single node"""
        raise NotImplementedError

    @abstractmethod
    def remove(self, checksum_address: str) -> bool:
        """Remove a single stored node"""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> bool:
        """Remove all stored nodes"""
        raise NotImplementedError

    @abstractmethod
    def payload(self) -> str:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_payload(self, data: str, *args, **kwargs) -> 'NodeStorage':
        """Instantiate a storage object from a dictionary"""
        raise NotImplementedError

    @abstractmethod
    def initialize(self):
        """One-time initialization steps to establish a node storage backend"""
        raise NotImplementedError


class InMemoryNodeStorage(NodeStorage):

    _name = 'memory'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__known_nodes = dict()

    def all(self, federated_only: bool) -> set:
        return set(self.__known_nodes.values())

    def get(self, checksum_address: str, federated_only: bool):
        try:
            return self.__known_nodes[checksum_address]
        except KeyError:
            raise self.UnknownNode

    def save(self, node):
        self.__known_nodes[node.checksum_public_address] = node
        return True

    def remove(self, checksum_address: str) -> bool:
        del self.__known_nodes[checksum_address]
        return True

    def clear(self):
        self.__known_nodes = dict()

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


class LocalFileBasedNodeStorage(NodeStorage):

    _name = 'local'
    __FILENAME_TEMPLATE = '{}.node'
    __DEFAULT_DIR = os.path.join(DEFAULT_CONFIG_ROOT, 'known_nodes', 'metadata')

    class NoNodeMetadataFileFound(FileNotFoundError, NodeStorage.UnknownNode):
        pass

    def __init__(self,
                 known_metadata_dir: str = __DEFAULT_DIR,
                 *args, **kwargs
                 ) -> None:

        super().__init__(*args, **kwargs)
        self.log = Logger(self.__class__.__name__)
        self.known_metadata_dir = known_metadata_dir

    def __generate_filepath(self, checksum_address: str) -> str:
        metadata_path = os.path.join(self.known_metadata_dir, self.__FILENAME_TEMPLATE.format(checksum_address))
        return metadata_path

    def __read(self, filepath: str, federated_only: bool):
        from nucypher.characters.lawful import Ursula
        try:
            with open(filepath, "rb") as seed_file:
                seed_file.seek(0)
                node_bytes = self.deserializer(seed_file.read())
                node = Ursula.from_bytes(node_bytes, federated_only=federated_only)
        except FileNotFoundError:
            raise self.UnknownNode
        return node

    def __write(self, filepath: str, node):
        with open(filepath, "wb") as f:
            f.write(self.serializer(self.character_class.__bytes__(node)))
        self.log.info("Wrote new node metadata to filesystem {}".format(filepath))
        return filepath

    def all(self, federated_only: bool) -> set:
        filenames = os.listdir(self.known_metadata_dir)
        self.log.info("Found {} known node metadata files at {}".format(len(filenames), self.known_metadata_dir))
        known_nodes = set()
        for filename in filenames:
            metadata_path = os.path.join(self.known_metadata_dir, filename)
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

    def clear(self):
        self.__known_nodes = dict()

    def payload(self) -> str:
        payload = {
            'storage_type': self._name,
            'known_metadata_dir': self.known_metadata_dir
        }
        return payload

    @classmethod
    def from_payload(cls, payload: dict, *args, **kwargs) -> 'LocalFileBasedNodeStorage':
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


class TemporaryFileBasedNodeStorage(LocalFileBasedNodeStorage):
    _name = 'tmp'

    def __init__(self, *args, **kwargs):
        self.__temp_dir = constants.NO_STORAGE_AVAILIBLE
        super().__init__(known_metadata_dir=self.__temp_dir, *args, **kwargs)

    def __del__(self):
        if not self.__temp_dir is constants.NO_STORAGE_AVAILIBLE:
            shutil.rmtree(self.__temp_dir, ignore_errors=True)

    def initialize(self):
        self.__temp_dir = tempfile.mkdtemp(prefix="nucypher-tmp-nodes-")
        self.known_metadata_dir = self.__temp_dir


class S3NodeStorage(NodeStorage):
    S3_ACL = 'private'  # Canned S3 Permissions

    def __init__(self,
                 bucket_name: str,
                 s3_resource=None,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)
        self.__bucket_name = bucket_name
        self.__s3client = boto3.client('s3')
        self.__s3resource = s3_resource or boto3.resource('s3')
        self.__bucket = constants.NO_STORAGE_AVAILIBLE

    @property
    def bucket(self):
        return self.__bucket

    @property
    def bucket_name(self):
        return self.__bucket_name

    def __read(self, node_obj: str):
        try:
            node_object_metadata = node_obj.get()
        except ClientError:
            raise self.UnknownNode
        node_bytes = self.deserializer(node_object_metadata['Body'].read())
        node = self.character_class.from_bytes(node_bytes)
        return node

    def generate_presigned_url(self, checksum_address: str) -> str:
        payload = {'Bucket': self.__bucket_name, 'Key': checksum_address}
        url = self.__s3client.generate_presigned_url('get_object', payload, ExpiresIn=900)
        return url

    def all(self, federated_only: bool) -> set:
        node_objs = self.__bucket.objects.all()
        nodes = set()
        for node_obj in node_objs:
            node = self.__read(node_obj=node_obj)
            nodes.add(node)
        return nodes

    def get(self, checksum_address: str, federated_only: bool):
        node_obj = self.__bucket.Object(checksum_address)
        node = self.__read(node_obj=node_obj)
        return node

    def save(self, node):
        self.__s3client.put_object(Bucket=self.__bucket_name,
                                   ACL=self.S3_ACL,
                                   Key=node.checksum_public_address,
                                   Body=self.serializer(bytes(node)))

    def remove(self, checksum_address: str) -> bool:
        node_obj = self.__bucket.Object(checksum_address)
        response = node_obj.delete()
        if response['ResponseMetadata']['HTTPStatusCode'] != 204:
            raise self.NodeStorageError("S3 Storage failed to delete node {}".format(checksum_address))
        return True

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
        self.__bucket = self.__s3resource.Bucket(self.__bucket_name)


### Node Storage Registry ###
NODE_STORAGES = {storage_class._name: storage_class for storage_class in NodeStorage.__subclasses__()}
