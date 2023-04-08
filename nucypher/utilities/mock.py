import json

from ferveo_py import Ciphertext, DecryptionShare

from nucypher_core import Conditions, Context


class ThresholdDecryptionRequest:
    def __init__(self,
                 ritual_id: int,
                 ciphertext: Ciphertext,
                 conditions: Conditions,
                 context: Context = None):
        self.ciphertext = ciphertext
        self.conditions = conditions
        self.context = context
        self.ritual_id = ritual_id

    @classmethod
    def from_bytes(cls, data: bytes):
        payload = json.loads(data.decode())
        return cls(
            ritual_id=int(payload['ritual_id']),
            ciphertext=Ciphertext.from_bytes(bytes.fromhex(payload['ciphertext'])),
            conditions=Conditions(bytes.fromhex(payload['conditions']).decode()),
            context=Context(bytes.fromhex(payload['context']).decode()) if 'context' in payload else None,
        )

    def __bytes__(self) -> bytes:
        payload = {
            'ritual_id': int(self.ritual_id),
            'ciphertext': bytes(self.ciphertext).hex(),
            'conditions': str(self.conditions).encode().hex(),
        }
        if self.context:
            payload['context'] = bytes(self.context).hex()
        return json.dumps(payload).encode()


class ThresholdDecryptionResponse:

    def __init__(self, decryption_share: DecryptionShare):
        self.decryption_share = decryption_share

    def __bytes__(self) -> bytes:
        data = {
            'decryption_share': bytes(self.decryption_share).hex(),
        }
        payload = json.dumps(data).encode()
        return payload
