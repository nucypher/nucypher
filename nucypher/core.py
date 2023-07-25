import base64
import json
from typing import Dict, NamedTuple

from nucypher_core.ferveo import Ciphertext, DkgPublicKey

from nucypher.policy.conditions.types import Lingo


class AccessControlPolicy(NamedTuple):
    public_key: DkgPublicKey
    conditions: Lingo  # should this be folded into aad?
    authorization: bytes

    def to_dict(self):
        d = {
            "public_key": base64.b64encode(bytes(self.public_key)).decode(),
            "access_conditions": self.conditions,
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
            conditions=acp_dict["access_conditions"],
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


class DkgMessageKit(NamedTuple):
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
    def from_dict(cls, message_kit: Dict) -> "DkgMessageKit":
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
    def from_bytes(cls, data: bytes) -> "DkgMessageKit":
        json_payload = base64.b64decode(data).decode()
        instance = cls.from_dict(json.loads(json_payload))
        return instance
