from nucypher_core import *
from nucypher_core import MessageKit as CoreMessageKit
from nucypher_core import ReencryptionRequest as CoreReencryptionRequest
from nucypher_core import RetrievalKit as CoreRetrievalKit
from typing import Optional, Tuple, Dict, Union, List

from nucypher.policy.conditions.evm import ContractCondition


class BoltOnConditions:
    _CORE_CLASS = NotImplemented
    _DELIMITER = b'0xBC'  # ESCAPE

    def __init__(self,
                 *args,
                 conditions: Optional['ConditionLingo'] = None,
                 core_instance: Optional = None,
                 **kwargs):
        if not core_instance:
            core_instance = self._CORE_CLASS(*args, **kwargs)
        self._core_instance = core_instance
        self.conditions = conditions

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self._core_instance, attr)

    def __bytes__(self):
        payload = bytes(self._core_instance)
        if self.conditions:
            payload += self._DELIMITER
            payload += bytes(self.conditions)
        return payload

    @classmethod
    def _parse(cls, data) -> Tuple[bytes, bytes]:
        if cls._DELIMITER in data:
            data, condition_bytes = data.split(cls._DELIMITER)
            return data, condition_bytes
        return data, b''  # TODO: Handle empty conditions better

    @classmethod
    def from_bytes(cls, data: bytes):
        condition = None
        if cls._DELIMITER in data:
            data, condition_bytes = cls._parse(data)
            condition = ContractCondition.from_bytes(condition_bytes)
        core_instance = cls._CORE_CLASS.from_bytes(data)
        instance = cls(core_instance=core_instance, decryption_condition=condition)
        return instance


class RetrievalKit(BoltOnConditions):
    _CORE_CLASS = CoreRetrievalKit

    @classmethod
    def from_message_kit(cls, message_kit: MessageKit, *args, **kwargs):
        # TODO: strip away the conditions for the lower layer
        data, condition_bytes = cls._parse(bytes(message_kit))
        core_mk_instance = MessageKit._CORE_CLASS.from_bytes(data)
        core_instance = cls._CORE_CLASS.from_message_kit(message_kit=core_mk_instance, *args, **kwargs)
        instance = cls(core_instance=core_instance)
        return instance


class MessageKit(BoltOnConditions):
    _CORE_CLASS = CoreMessageKit


class ReencryptionRequest(BoltOnConditions):
    _CORE_CLASS = CoreReencryptionRequest

    def __init__(self, context: Optional[Dict[str, Union[str, int]]] = None, *args, **kwargs):
        self.context = context
        super().__init__(*args, **kwargs)
