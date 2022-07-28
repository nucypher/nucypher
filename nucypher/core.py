from nucypher_core import *
from nucypher_core import MessageKit as CoreMessageKit
from nucypher_core import ReencryptionRequest as CoreReencryptionRequest
from nucypher_core import RetrievalKit as CoreRetrievalKit
from typing import Optional

from nucypher.policy.conditions.evm import EVMCondition


class BoltOnConditions:
    _CORE_CLASS = NotImplemented
    _DELIMITER = b'0xBC'  # ESCAPE

    def __init__(self,
                 *args,
                 condition: Optional[EVMCondition] = None,
                 core_instance: Optional = None,
                 **kwargs):
        if not core_instance:
            core_instance = self._CORE_CLASS(*args, **kwargs)
        self._core_instance = core_instance
        self.condition = condition

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._core_instance, attr)

    def __bytes__(self):
        payload = bytes(self._core_instance)
        if self.condition:
            payload += self._DELIMITER
            payload += bytes(self.condition)
        return payload

    @classmethod
    def from_bytes(cls, data: bytes):
        condition = None
        if cls._DELIMITER in data:
            data, condition_bytes = data.split(cls._DELIMITER)
            condition = EVMCondition.from_bytes(condition_bytes)
        core_instance = cls._CORE_CLASS.from_bytes(data)
        instance = cls(core_instance=core_instance, decryption_condition=condition)
        return instance


class RetrievalKit(BoltOnConditions):
    _CORE_CLASS = CoreRetrievalKit


class MessageKit(BoltOnConditions):
    _CORE_CLASS = CoreMessageKit


class ReencryptionRequest(BoltOnConditions):
    _CORE_CLASS = CoreReencryptionRequest
