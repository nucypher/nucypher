import os
from abc import ABC, abstractmethod
from typing import Iterator, List, Union

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.policy.collections import PolicyCredential


class PolicyCredentialStorage(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def save(self, credential: PolicyCredential):
        raise NotImplementedError

    @abstractmethod
    def load(self, policy_id: bytes) -> 'PolicyCredential':
        pass

    @abstractmethod
    def all(self) -> List['PolicyCredential']:
        raise NotImplementedError

    @abstractmethod
    def remove(self, policy_id: Union[str, hex]) -> None:
        raise NotImplementedError


class InMemoryPolicyCredentialStorage(PolicyCredentialStorage):

    def __init__(self):
        self.__credentials = dict()
        super().__init__()

    def save(self, credential: PolicyCredential):
        self.__credentials[credential.id] = credential

    def load(self, policy_id: bytes) -> PolicyCredential:
        credential = self.__credentials[policy_id]
        return credential

    def all(self) -> List['PolicyCredential']:
        credentials = list(self.__credentials.values())
        return credentials

    def remove(self, policy_id: Union[str, hex]) -> None:
        del self.__credentials[policy_id]

    def clear(self) -> None:
        self.__credentials = dict()


class LocalFilePolicyCredentialStorage(PolicyCredentialStorage):

    _default_credential_dir = os.path.join(DEFAULT_CONFIG_ROOT, 'credentials')
    extension = 'cred'

    def __init__(self, credential_dir: str = _default_credential_dir):
        self.credential_dir = credential_dir
        if not os.path.exists(self.credential_dir):
            os.mkdir(credential_dir)
        super().__init__()

    def save(self, credential: PolicyCredential, filepath: str = None) -> str:
        if not filepath:
            filename = f'{credential.id.hex()}.{self.extension}'
            filepath = os.path.join(self.credential_dir, filename)
        with open(filepath, 'w') as file:
            file.write(credential.to_json())
        return filepath

    def load(self, policy_id: Union[str, hex] = None, filepath: str = None) -> PolicyCredential:
        if not filepath and not policy_id:
            raise ValueError("Cannot load credential: "
                             "Policy ID or filepath must be passed, got neither.")
        if not filepath:
            if isinstance(policy_id, bytes):
                policy_id = policy_id.hex()
            filename = f'{policy_id}.{self.extension}'
            filepath = os.path.join(self.credential_dir, filename)
        try:
            with open(filepath) as file:
                data = file.read()
                credential = PolicyCredential.from_json(data)
        except FileNotFoundError:
            raise FileNotFoundError(f"Policy {filepath} is not stored "
                                    f"at {self.credential_dir}.")
        return credential

    def all(self) -> Iterator:
        for filepath in os.listdir(self.credential_dir):
            yield self.load(filepath=os.path.join(self.credential_dir, filepath))

    def remove(self, policy_id: Union[str, hex]) -> None:
        if isinstance(policy_id, bytes):
            policy_id = policy_id.hex()
        filename = f'{policy_id}.{self.extension}'
        filepath = os.path.join(self.credential_dir, filename)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            raise FileNotFoundError(f"Policy {policy_id} is not stored "
                                    f"at {self.credential_dir}")
