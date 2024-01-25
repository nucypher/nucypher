import inspect
from typing import List, Optional, Tuple, Union

from eth_typing.evm import ChecksumAddress
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    SessionSecretFactory,
    SessionStaticKey,
    SessionStaticSecret,
    ThresholdDecryptionRequest,
    ThresholdDecryptionResponse,
    ferveo,
)
from nucypher_core.ferveo import (
    AggregatedTranscript,
    CiphertextHeader,
    DecryptionSharePrecomputed,
    DecryptionShareSimple,
    DkgPublicKey,
    FerveoVariant,
    Transcript,
    Validator,
)
from nucypher_core.umbral import PublicKey, SecretKey, SecretKeyFactory, generate_kfrags

from nucypher.crypto import keypairs
from nucypher.crypto.ferveo import dkg
from nucypher.crypto.keypairs import (
    DecryptingKeypair,
    HostingKeypair,
    RitualisticKeypair,
    SigningKeypair,
)


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoDecryptingPower(PowerUpError):
    pass

class NoRitualisticPower(PowerUpError):
    pass


class NotImplmplemented(PowerUpError):
    pass

class NoThresholdRequestDecryptingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups: list = None) -> None:
        self.__power_ups = {}  # type: dict
        # TODO: The keys here will actually be IDs for looking up in a Datastore.
        self.public_keys = {}  # type: dict

        if power_ups is not None:
            for power_up in power_ups:
                self.consume_power_up(power_up)

    def __contains__(self, item):
        try:
            self.power_ups(item)
        except PowerUpError:
            return False
        else:
            return True

    def consume_power_up(self, power_up, *args, **kwargs):
        if isinstance(power_up, CryptoPowerUp):
            power_up_class = power_up.__class__
            power_up.activate(*args, **kwargs)
            power_up_instance = power_up
        elif CryptoPowerUp in inspect.getmro(power_up):
            power_up_class = power_up
            power_up_instance = power_up()
        else:
            raise TypeError(
                ("power_up must be a subclass of CryptoPowerUp or an instance "
                 "of a CryptoPowerUp subclass."))
        self.__power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()

    def power_ups(self, power_up_class):
        try:
            return self.__power_ups[power_up_class]
        except KeyError:
            raise power_up_class.not_found_error


class CryptoPowerUp:
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False

    def activate(self, *args, **kwargs):
        return


class KeyPairBasedPower(CryptoPowerUp):
    confers_public_key = True
    _keypair_class = keypairs.Keypair
    _default_private_key_class = SecretKey

    def __init__(self, public_key: PublicKey = None, keypair: keypairs.Keypair = None):
        if keypair and public_key:
            raise ValueError("Pass keypair or pubkey_bytes (or neither), but not both.")
        elif keypair:
            self.keypair = keypair
        else:
            # They didn't pass a keypair; we'll make one with the bytes or
            # Umbral PublicKey if they provided such a thing.
            if public_key:
                try:
                    public_key = public_key.as_umbral_pubkey()
                except AttributeError:
                    try:
                        public_key = PublicKey.from_compressed_bytes(public_key)
                    except TypeError:
                        public_key = public_key
                self.keypair = self._keypair_class(
                    public_key=public_key)
            else:
                # They didn't even pass a public key.  We have no choice but to generate a keypair.
                self.keypair = self._keypair_class(generate_keys_if_needed=True)

    def __getattr__(self, item):
        if item in self.provides:
            try:
                return getattr(self.keypair, item)
            except AttributeError:
                message = f"This {self.__class__} has a keypair, {self.keypair.__class__}, which doesn't provide {item}."
                raise PowerUpError(message)
        else:
            raise PowerUpError("This {} doesn't provide {}.".format(self.__class__, item))

    def public_key(self) -> 'PublicKey':
        return self.keypair.pubkey


class SigningPower(KeyPairBasedPower):
    _keypair_class = SigningKeypair
    not_found_error = NoSigningPower
    provides = ("sign", "get_signature_stamp")


class DecryptingPower(KeyPairBasedPower):
    _keypair_class = DecryptingKeypair
    not_found_error = NoDecryptingPower
    provides = ("decrypt_message_kit", "decrypt_kfrag", "decrypt_treasure_map")


class RitualisticPower(KeyPairBasedPower):
    _keypair_class = RitualisticKeypair
    _default_private_key_class = ferveo.Keypair

    not_found_error = NoRitualisticPower
    provides = ("derive_decryption_share", "generate_transcript")

    def derive_decryption_share(
        self,
        checksum_address: ChecksumAddress,
        ritual_id: int,
        shares: int,
        threshold: int,
        nodes: list,
        aggregated_transcript: AggregatedTranscript,
        ciphertext_header: CiphertextHeader,
        aad: bytes,
        variant: FerveoVariant,
    ) -> Union[DecryptionShareSimple, DecryptionSharePrecomputed]:
        decryption_share = dkg.derive_decryption_share(
            ritual_id=ritual_id,
            me=Validator(address=checksum_address, public_key=self.keypair.pubkey),
            shares=shares,
            threshold=threshold,
            nodes=nodes,
            aggregated_transcript=aggregated_transcript,
            keypair=self.keypair._privkey,
            ciphertext_header=ciphertext_header,
            aad=aad,
            variant=variant
        )
        return decryption_share

    def generate_transcript(
            self,
            checksum_address: ChecksumAddress,
            ritual_id: int,
            shares: int,
            threshold: int,
            nodes: list
    ) -> Transcript:
        transcript = dkg.generate_transcript(
            ritual_id=ritual_id,
            me=Validator(address=checksum_address, public_key=self.keypair.pubkey),
            shares=shares,
            threshold=threshold,
            nodes=nodes
        )
        return transcript

    def aggregate_transcripts(
            self,
            ritual_id: int,
            checksum_address: ChecksumAddress,
            shares: int,
            threshold: int,
            transcripts: list
    ) -> Tuple[AggregatedTranscript, DkgPublicKey]:
        aggregated_transcript, dkg_public_key = dkg.aggregate_transcripts(
            ritual_id=ritual_id,
            me=Validator(address=checksum_address, public_key=self.keypair.pubkey),
            shares=shares,
            threshold=threshold,
            transcripts=transcripts
        )
        return aggregated_transcript, dkg_public_key


class DerivedKeyBasedPower(CryptoPowerUp):
    """
    Rather than rely on an established KeyPair, this type of power
    derives a key at moments defined by the user.
    """


class ThresholdRequestDecryptingPower(DerivedKeyBasedPower):
    class ThresholdRequestDecryptionFailed(Exception):
        """Raised when decryption of the request fails."""

    class ThresholdResponseEncryptionFailed(Exception):
        """Raised when encryption of response to request fails."""

    def __init__(self, session_secret_factory: Optional[SessionSecretFactory] = None):
        if not session_secret_factory:
            session_secret_factory = SessionSecretFactory.random()
        self.__request_key_factory = session_secret_factory

    def _get_static_secret_from_ritual_id(self, ritual_id: int) -> SessionStaticSecret:
        return self.__request_key_factory.make_key(bytes(ritual_id.to_bytes(4, "big")))

    def get_pubkey_from_ritual_id(self, ritual_id: int) -> SessionStaticKey:
        return self._get_static_secret_from_ritual_id(ritual_id).public_key()

    def decrypt_encrypted_request(
        self, encrypted_request: EncryptedThresholdDecryptionRequest
    ) -> ThresholdDecryptionRequest:
        try:
            static_secret = self._get_static_secret_from_ritual_id(
                encrypted_request.ritual_id
            )
            requester_public_key = encrypted_request.requester_public_key
            shared_secret = static_secret.derive_shared_secret(requester_public_key)
            decrypted_request = encrypted_request.decrypt(shared_secret)
            return decrypted_request
        except Exception as e:
            raise self.ThresholdRequestDecryptionFailed from e

    def encrypt_decryption_response(
        self,
        decryption_response: ThresholdDecryptionResponse,
        requester_public_key: SessionStaticKey,
    ) -> EncryptedThresholdDecryptionResponse:
        try:
            static_secret = self._get_static_secret_from_ritual_id(
                decryption_response.ritual_id
            )
            shared_secret = static_secret.derive_shared_secret(requester_public_key)
            encrypted_decryption_response = decryption_response.encrypt(shared_secret)
            return encrypted_decryption_response
        except Exception as e:
            raise self.ThresholdResponseEncryptionFailed from e


class DelegatingPower(DerivedKeyBasedPower):

    def __init__(self, secret_key_factory: Optional[SecretKeyFactory] = None):
        if not secret_key_factory:
            secret_key_factory = SecretKeyFactory.random()
        self.__secret_key_factory = secret_key_factory

    def _get_privkey_from_label(self, label):
        return self.__secret_key_factory.make_key(label)

    def get_pubkey_from_label(self, label):
        return self._get_privkey_from_label(label).public_key()

    def generate_kfrags(self,
                        bob_pubkey_enc,
                        signer,
                        label: bytes,
                        threshold: int,
                        shares: int
                        ) -> Tuple[PublicKey, List]:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.
        :param bob_pubkey_enc: Bob's public key
        :param threshold: Minimum number of KFrags needed to rebuild ciphertext
        :param shares: Total number of KFrags to generate
        """

        __private_key = self._get_privkey_from_label(label)
        kfrags = generate_kfrags(delegating_sk=__private_key,
                                 receiving_pk=bob_pubkey_enc,
                                 threshold=threshold,
                                 shares=shares,
                                 signer=signer,
                                 sign_delegating_key=False,
                                 sign_receiving_key=False,
                                 )
        return __private_key.public_key(), kfrags

    def get_decrypting_power_from_label(self, label):
        label_privkey = self._get_privkey_from_label(label)
        label_keypair = keypairs.DecryptingKeypair(private_key=label_privkey)
        decrypting_power = DecryptingPower(keypair=label_keypair)
        return decrypting_power


class TLSHostingPower(KeyPairBasedPower):
    _keypair_class = HostingKeypair
    provides = ("get_deployer",)

    class NoHostingPower(PowerUpError):
        pass

    not_found_error = NoHostingPower

    def __init__(self,
                 host: str,
                 public_certificate=None,
                 public_certificate_filepath=None,
                 *args, **kwargs) -> None:

        if public_certificate and public_certificate_filepath:
            # TODO: Design decision here: if they do pass both, and they're identical, do we let that slide?  NRN
            raise ValueError("Pass either a public_certificate or a public_certificate_filepath, not both.")

        if public_certificate:
            kwargs['keypair'] = HostingKeypair(certificate=public_certificate, host=host)
        elif public_certificate_filepath:
            kwargs['keypair'] = HostingKeypair(certificate_filepath=public_certificate_filepath, host=host)
        super().__init__(*args, **kwargs)
