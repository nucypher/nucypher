import umbral
from umbral import VerificationError

from nucypher.crypto.passwords import derive_key_from_password, SecretBox


SIGNATURE_DST = b'SIGNATURE'


def hash_to_curvebn():
    raise NotImplementedError


class Signer(umbral.signing.Signer):

    def __init__(self, private_key):
        assert isinstance(private_key, umbral.SecretKey)
        super().__init__(private_key)

    def __call__(self, message):
        return Signature.from_bytes(bytes(self.sign(message)))


class CryptographyPrivkey:

    def __init__(self, secret_key):
        self._secret_key = secret_key

    def sign(self, message, ecdsa):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        assert isinstance(ecdsa.algorithm, hashes.SHA256)

        # NOTE: returns just r and s, not a DER format!
        # change `signature_der_bytes` at the usage locations accordingly if that stays.
        signer = Signer(self._secret_key)
        return bytes(signer(message))


class CryptographyPubkey:

    def __init__(self, public_key):
        assert isinstance(public_key, UmbralPublicKey)
        self._public_key = public_key

    def verify(self, signature, message, ecdsa):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        assert isinstance(ecdsa.algorithm, hashes.SHA256)

        # NOTE: returns just r and s, not a DER format!
        # change `signature_der_bytes` at the usage locations accordingly if that stays.
        signature = Signature.from_bytes(signature)
        return signature.verify(message, self._public_key)


class AuthenticationFailed(Exception):
    pass


class UmbralPrivateKey(umbral.SecretKey):

    @classmethod
    def gen_key(cls):
        return cls.random()

    def get_pubkey(self):
        return UmbralPublicKey.from_secret_key(self)

    def to_bytes(self, wrapping_key=None):
        if wrapping_key is None:
            return bytes(self)
        else:
            return SecretBox(wrapping_key).encrypt(bytes(self))

    @classmethod
    def from_bytes(cls, key_bytes, wrapping_key=None):
        if wrapping_key is None:
            data = key_bytes
        else:
            try:
                data = SecretBox(wrapping_key).decrypt(key_bytes)
            except CryptoError:
                raise AuthenticationFailed()
        key = super().from_bytes(data)
        key.__class__ = cls
        return key

    @property
    def pubkey(self):
        return self.get_pubkey()

    def to_cryptography_privkey(self):
        return CryptographyPrivkey(self)

    def __eq__(self, other):
        if not isinstance(other, UmbralPrivateKey):
            return False
        return super().__eq__(other)


class UmbralPublicKey(umbral.PublicKey):

    def to_bytes(self):
        return bytes(self)

    def to_cryptography_pubkey(self):
        return CryptographyPubkey(self)

    def hex(self):
        return bytes(self).hex()

    @classmethod
    def from_hex(cls, data):
        return cls.from_bytes(bytes.fromhex(data))


class UmbralKeyingMaterial(umbral.SecretKeyFactory):

    def __init__(self):
        skf = umbral.SecretKeyFactory.random()
        self._SecretKeyFactory__key_seed = skf._SecretKeyFactory__key_seed

    @classmethod
    def from_bytes(cls, key_bytes, password):
        assert password is None
        skf = umbral.SecretKeyFactory.from_bytes(key_bytes)
        res = cls()
        res._SecretKeyFactory__key_seed = skf._SecretKeyFactory__key_seed
        return res

    def to_bytes(self):
        return bytes(self)

    def derive_privkey_by_label(self, label):
        pk = self.secret_key_by_label(label)
        pk.__class__ = UmbralPrivateKey
        return pk


class Signature(umbral.signing.Signature):

    @classmethod
    def from_bytes(cls, data, der_encoded=False):
        # NOTE: returns just r and s, not a DER format!
        # change `signature_der_bytes` at the usage locations accordingly if that stays.
        return super(Signature, cls).from_bytes(data)

    def verify(self, message, verifying_key, is_prehashed=False):
        assert not is_prehashed
        return super().verify(verifying_key, message)

    def __add__(self, other):
        return bytes(self) + bytes(other)


class Capsule:

    def __init__(self, capsule):
        assert isinstance(capsule, umbral.Capsule)
        self._capsule = capsule
        self._cfrags = []

        self._delegating_key = None
        self._receiving_key = None
        self._verifying_key = None

    def attach_cfrag(self, cfrag):
        assert isinstance(cfrag, VerifiedCapsuleFrag)
        self._cfrags.append(cfrag)

    def clear_cfrags(self):
        self._cfrags = []

    @classmethod
    def serialized_size(cls):
        return umbral.Capsule.serialized_size()

    def set_correctness_keys(self, delegating=None, receiving=None, verifying=None):
        assert delegating is None or isinstance(delegating, UmbralPublicKey)
        assert receiving is None or isinstance(receiving, UmbralPublicKey)
        assert verifying is None or isinstance(verifying, UmbralPublicKey)

        if self._delegating_key is None:
            self._delegating_key = delegating
        elif delegating is not None and delegating != self._delegating_key:
            raise Exception("Replacing existing delegating key")

        if self._receiving_key is None:
            self._receiving_key = receiving
        elif receiving is not None and receiving != self._receiving_key:
            raise Exception("Replacing existing receiving key")

        if self._verifying_key is None:
            self._verifying_key = verifying
        elif verifying is not None and verifying != self._verifying_key:
            raise Exception("Replacing existing verifying key")

    def get_correctness_keys(self):
        return dict(delegating=self._delegating_key,
                    receiving=self._receiving_key,
                    verifying=self._verifying_key)

    def __bytes__(self):
        return bytes(self._capsule)

    def to_bytes(self):
        return bytes(self._capsule)

    def __len__(self):
        return len(self._cfrags)

    @classmethod
    def from_bytes(cls, data):
        return cls(umbral.Capsule.from_bytes(data))

    def __eq__(self, other):
        return self._capsule == other._capsule

    def __hash__(self):
        return hash(self._capsule)


class KFrag(umbral.KeyFrag):

    def verify(self, signing_pubkey, delegating_pubkey=None, receiving_pubkey=None):
        return super().verify(verifying_pk=signing_pubkey,
                              delegating_pk=delegating_pubkey,
                              receiving_pk=receiving_pubkey)


VerifiedKeyFrag = umbral.VerifiedKeyFrag

VerifiedCapsuleFrag = umbral.VerifiedCapsuleFrag


class CapsuleFrag(umbral.CapsuleFrag):

    def to_bytes(self):
        return bytes(self)

    def verify_correctness(self, capsule):
        keys = capsule.get_correctness_keys()
        return self.verify(
            capsule._capsule,
            verifying_pk=keys['verifying'], delegating_pk=keys['delegating'], receiving_pk=keys['receiving'])


# Adapter for standalone functions
class PRE:

    GenericUmbralError = umbral.GenericError

    @staticmethod
    def reencrypt(kfrag, capsule):
        assert isinstance(capsule, Capsule)
        cf = umbral.reencrypt(capsule._capsule, kfrag)
        return cf

    @staticmethod
    def encrypt(pubkey, message):
        capsule, ciphertext = umbral.encrypt(pubkey, message)
        return ciphertext, Capsule(capsule)

    @staticmethod
    def decrypt(ciphertext, capsule, decrypting_key):
        assert isinstance(capsule, Capsule)
        if len(capsule) == 0:
            return umbral.decrypt_original(decrypting_key, capsule._capsule, ciphertext)
        else:
            return umbral.decrypt_reencrypted(
                decrypting_key, capsule._delegating_key, capsule._capsule, capsule._cfrags, ciphertext)

    @staticmethod
    def generate_kfrags(delegating_privkey,
                        receiving_pubkey,
                        threshold,
                        N,
                        signer,
                        sign_delegating_key=False,
                        sign_receiving_key=False,
                        ):
        if 'SignatureStamp' in str(type(signer)):
            signer = signer._SignatureStamp__signer # TODO: gotta be a better way

        kfrags = umbral.generate_kfrags(
            delegating_sk=delegating_privkey,
            receiving_pk=receiving_pubkey,
            signer=signer,
            threshold=threshold,
            num_kfrags=N,
            sign_delegating_key=sign_delegating_key,
            sign_receiving_key=sign_receiving_key)

        return kfrags

    @staticmethod
    def _encapsulate(delegating_pubkey):
        capsule, key_seed = umbral.Capsule.from_public_key(delegating_pubkey)
        return bytes(key_seed), Capsule(capsule)


pre = PRE()
