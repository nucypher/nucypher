import base64
import json
from typing import Dict, NamedTuple, Optional

from nucypher_core import Conditions, Context, SessionSharedSecret, SessionStaticKey
from nucypher_core.ferveo import Ciphertext, DkgPublicKey


class AccessControlPolicy(NamedTuple):
    public_key: DkgPublicKey
    conditions: Conditions  # should this be folded into aad?
    authorization: bytes

    def to_dict(self):
        d = {
            "public_key": base64.b64encode(bytes(self.public_key)).decode(),
            "access_conditions": str(self.conditions),
            "authorization": {
                "evidence": base64.b64encode(self.authorization).decode(),
            },
        }

        return d

    @classmethod
    def from_dict(cls, acp_dict: Dict) -> "AccessControlPolicy":
        return cls(
            public_key=DkgPublicKey.from_bytes(
                base64.b64decode(acp_dict["public_key"])
            ),
            conditions=Conditions(acp_dict["access_conditions"]),
            authorization=base64.b64decode(acp_dict["authorization"]["evidence"]),
        )

    def __bytes__(self):
        json_payload = json.dumps(self.to_dict()).encode()
        b64_json_payload = base64.b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "AccessControlPolicy":
        json_payload = base64.b64decode(data).decode()
        instance = cls.from_dict(json.loads(json_payload))
        return instance


class ThresholdMessageKit(NamedTuple):
    # one entry for now: thin ferveo ciphertext + symmetric ciphertext; ferveo#147
    ciphertext: Ciphertext
    acp: AccessControlPolicy

    def to_dict(self):
        d = {
            "ciphertext": base64.b64encode(bytes(self.ciphertext)).decode(),
            "acp": self.acp.to_dict(),
        }

        return d

    @classmethod
    def from_dict(cls, message_kit: Dict) -> "ThresholdMessageKit":
        return cls(
            ciphertext=Ciphertext.from_bytes(
                base64.b64decode(message_kit["ciphertext"])
            ),
            acp=AccessControlPolicy.from_dict(message_kit["acp"]),
        )

    def __bytes__(self):
        json_payload = json.dumps(self.to_dict()).encode()
        b64_json_payload = base64.b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "ThresholdMessageKit":
        json_payload = base64.b64decode(data).decode()
        instance = cls.from_dict(json.loads(json_payload))
        return instance


class ThresholdDecryptionRequest(NamedTuple):
    ritual_id: int
    access_control_policy: AccessControlPolicy
    variant: int
    ciphertext: Ciphertext
    context: Optional[Context]

    def encrypt(
        self, shared_secret: SessionSharedSecret, requester_public_key: SessionStaticKey
    ) -> "EncryptedThresholdDecryptionRequest":
        return EncryptedThresholdDecryptionRequest(
            ritual_id=self.ritual_id,
            requester_public_key=requester_public_key,
            request_bytes=bytes(self),
        )

    def _to_dict(self):
        d = {
            "ritual_id": self.ritual_id,
            "acp": self.access_control_policy.to_dict(),
            "variant": self.variant,
            "ciphertext": base64.b64encode(bytes(self.ciphertext)).decode(),
        }

        # optional
        if self.context:
            d["context"] = str(self.context)

        return d

    @classmethod
    def _from_dict(cls, encrypted_request_dict: Dict) -> "ThresholdDecryptionRequest":
        context = encrypted_request_dict.get("context")
        if context:
            context = Context.from_string(context)

        return cls(
            ritual_id=encrypted_request_dict["ritual_id"],
            access_control_policy=AccessControlPolicy.from_dict(
                encrypted_request_dict["acp"]
            ),
            variant=encrypted_request_dict["variant"],
            ciphertext=Ciphertext.from_bytes(
                base64.b64decode(encrypted_request_dict["ciphertext"])
            ),
            context=context,
        )

    def __bytes__(self) -> bytes:
        json_payload = json.dumps(self._to_dict()).encode()
        b64_json_payload = base64.b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "ThresholdDecryptionRequest":
        json_payload = base64.b64decode(data).decode()
        instance = cls._from_dict(json.loads(json_payload))
        return instance


class EncryptedThresholdDecryptionRequest:
    def __init__(
        self,
        ritual_id: int,
        requester_public_key: SessionStaticKey,
        request_bytes: bytes,
    ):
        self.ritual_id = ritual_id
        self.requester_public_key = requester_public_key
        self.__request_bytes = request_bytes  # pretend that this gets encrypted

    def decrypt(self, shared_secret: SessionSharedSecret) -> ThresholdDecryptionRequest:
        return ThresholdDecryptionRequest.from_bytes(
            self.__request_bytes
        )  # pretend this is decrypted

    def _to_dict(self):
        d = {
            "ritual_id": self.ritual_id,
            "requester_public_key": base64.b64encode(
                bytes(self.requester_public_key)
            ).decode(),
            "request_bytes": base64.b64encode(self.__request_bytes).decode(),
        }

        return d

    @classmethod
    def _from_dict(cls, encrypted_request_dict: Dict):
        return cls(
            ritual_id=encrypted_request_dict["ritual_id"],
            requester_public_key=SessionStaticKey.from_bytes(
                base64.b64decode(encrypted_request_dict["requester_public_key"])
            ),
            request_bytes=base64.b64decode(encrypted_request_dict["request_bytes"]),
        )

    def __bytes__(self) -> bytes:
        json_payload = json.dumps(self._to_dict()).encode()
        b64_json_payload = base64.b64encode(json_payload)
        return b64_json_payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedThresholdDecryptionRequest":
        json_payload = base64.b64decode(data).decode()
        instance = cls._from_dict(json.loads(json_payload))
        return instance
