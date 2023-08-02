import base64
import json
from typing import Callable, Dict, NamedTuple, Optional

from cryptography.fernet import Fernet
from nucypher_core import Conditions, Context, SessionSharedSecret, SessionStaticKey
from nucypher_core.ferveo import Ciphertext, DkgPublicKey, encrypt

from nucypher.crypto.utils import keccak_digest


class AccessControlPolicy(NamedTuple):
    public_key: DkgPublicKey
    conditions: Conditions
    authorization: bytes
    version: int = 1

    def aad(self) -> bytes:
        return str(self.conditions).encode()

    def to_dict(self):
        d = {
            "version": self.version,
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
            version=acp_dict["version"],
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


class ThresholdMessageKit:
    VERSION = 1

    def __init__(
        self,
        kem_ciphertext: Ciphertext,
        dem_ciphertext: bytes,
        acp: AccessControlPolicy,
        version: int = VERSION,
    ):
        self.version = version
        self.kem_ciphertext = kem_ciphertext
        self.dem_ciphertext = dem_ciphertext
        self.acp = acp

    @staticmethod
    def _validate_aad_compatibility(tmk_aad: bytes, acp_aad: bytes):
        if tmk_aad != acp_aad:
            raise ValueError("Incompatible ThresholdMessageKit and AccessControlPolicy")

    @classmethod
    def encrypt_data(
        cls,
        plaintext: bytes,
        conditions: Conditions,
        dkg_public_key: DkgPublicKey,
        signer: Callable[[bytes], bytes],
    ):
        symmetric_key = Fernet.generate_key()
        fernet = Fernet(symmetric_key)
        dem_ciphertext = fernet.encrypt(plaintext)

        aad = str(conditions).encode()
        kem_ciphertext = encrypt(symmetric_key, aad, dkg_public_key)

        kem_ciphertext_hash = keccak_digest(bytes(kem_ciphertext))
        authorization = signer(kem_ciphertext_hash)

        acp = AccessControlPolicy(
            public_key=dkg_public_key,
            conditions=conditions,
            authorization=authorization,
        )

        # we need to link the ThresholdMessageKit to a specific version of the ACP
        # because the ACP.aad() function should return the same value as the aad used
        # for encryption. Since the ACP version can change independently of
        # ThresholdMessageKit this check is good for code maintenance and ensuring
        # compatibility - unless we find a better way to link TMK and ACP.
        #
        # TODO: perhaps this can be improved. You could have ACP be an inner class of TMK,
        #  but not sure how that plays out with rust and python bindings... OR ...?
        cls._validate_aad_compatibility(aad, acp.aad())

        return ThresholdMessageKit(
            kem_ciphertext,
            dem_ciphertext,
            acp,
        )

    def to_dict(self):
        d = {
            "version": self.version,
            "kem_ciphertext": base64.b64encode(bytes(self.kem_ciphertext)).decode(),
            "dem_ciphertext": base64.b64encode(self.dem_ciphertext).decode(),
            "acp": self.acp.to_dict(),
        }

        return d

    @classmethod
    def from_dict(cls, message_kit: Dict) -> "ThresholdMessageKit":
        return cls(
            version=message_kit["version"],
            kem_ciphertext=Ciphertext.from_bytes(
                base64.b64decode(message_kit["kem_ciphertext"])
            ),
            dem_ciphertext=base64.b64decode(message_kit["dem_ciphertext"]),
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
