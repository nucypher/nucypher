import json
from typing import Dict, Tuple

from nucypher_core import (
    EncryptedThresholdDecryptionResponse,
    SessionSecretFactory,
    SessionStaticKey,
    ferveo,
)

from nucypher.characters.lawful import Bob, Enrico
from nucypher.cli.types import ChecksumAddress
from nucypher.crypto.powers import ThresholdRequestDecryptingPower
from nucypher.network.decryption import ThresholdDecryptionClient
from nucypher.policy.conditions.types import LingoList
from nucypher.policy.conditions.utils import validate_condition_lingo


class FakeNode:
    def __init__(self, checksum_address):
        self.checksum_address = checksum_address


class _ParticipantKeyDict(dict):
    def __init__(self, threshold_request_decrypting_power, *args, **kwargs):
        self.threshold_request_decrypting_power = threshold_request_decrypting_power
        super().__init__(*args, **kwargs)

    def __getitem__(self, _item):
        # Everybody has the same public key at the moment.
        fifty_fiver = (
            self.threshold_request_decrypting_power._get_static_secret_from_ritual_id(
                55
            )
        )
        return fifty_fiver.public_key()


class _FakeRitual:
    def __init__(
        self, tau, threshold, shares_num, checksum_addresses, session_seed=None
    ):
        self.tau = tau
        self.threshold = threshold
        self.shares = shares_num
        self.fake_nodes = [
            FakeNode(checksum_address) for checksum_address in checksum_addresses
        ]
        self.checksum_addresses = checksum_addresses
        if session_seed == None:
            session_seed = b"ABytestringOf32BytesIsNeededHere"
        secret_factory = SessionSecretFactory.from_secure_randomness(session_seed)
        self.threshold_request_decrypting_power = ThresholdRequestDecryptingPower(
            session_secret_factory=secret_factory
        )
        self.participant_public_keys = _ParticipantKeyDict(
            self.threshold_request_decrypting_power
        )


class DKGOmniscient:
    class DKGInsight:
        tau = 1
        security_threshold = 3
        shares_num = 4

        def __init__(self):
            """ """

            def gen_eth_addr(i: int) -> str:
                return f"0x{i:040x}"

            ### Here is the generation thing.
            validator_keypairs = [
                ferveo.Keypair.random() for _ in range(0, self.shares_num)
            ]

            validators = [
                ferveo.Validator(gen_eth_addr(i), keypair.public_key())
                for i, keypair in enumerate(validator_keypairs)
            ]

            # Validators must be sorted by their public key
            validators.sort(key=lambda v: v.address)

            # Each validator holds their own DKG instance and generates a transcript every
            # validator, including themselves
            self.aggregation_messages = []
            for sender in validators:
                dkg = ferveo.Dkg(
                    tau=self.tau,
                    shares_num=self.shares_num,
                    security_threshold=self.security_threshold,
                    validators=validators,
                    me=sender,
                )
                self.aggregation_messages.append((sender, dkg.generate_transcript()))

            self.dkg = dkg
            self.validators = validators
            self.validator_keypairs = validator_keypairs

            # Server can aggregate the transcripts
            self.server_aggregate = dkg.aggregate_transcripts(self.aggregation_messages)
            assert self.server_aggregate.verify(
                self.shares_num, self.aggregation_messages
            )

            # And the client can also aggregate and verify the transcripts
            self.client_aggregate = ferveo.AggregatedTranscript(
                self.aggregation_messages
            )
            assert self.server_aggregate.verify(
                self.shares_num, self.aggregation_messages
            )

    _dkg_insight = DKGInsight()


class NiceGuyEddie(Enrico, DKGOmniscient):
    """
    Like Enrico, but from Reswervoir Dogs.

    He doesn't know who's shot, who's not.
    """

    def __init__(self, encrypting_key, *args, **kwargs):
        # We're going to use the DKG public key as the encrypting key, and ignore the key passed in.
        encrypting_key_we_actually_want_to_use = self._dkg_insight.dkg.public_key
        super().__init__(encrypting_key_we_actually_want_to_use, *args, **kwargs)

    def encrypt_for_dkg(
        self, plaintext: bytes, conditions: LingoList
    ) -> ferveo.Ciphertext:
        """
        https://imgflip.com/i/7o0po4
        """
        validate_condition_lingo(conditions)
        conditions_bytes = json.dumps(conditions).encode()
        self._dkg_insight.conditions_bytes = conditions_bytes
        ciphertext = ferveo.encrypt(plaintext, conditions_bytes, self.policy_pubkey)
        return ciphertext


class BobGonnaBob(Bob, DKGOmniscient):
    """
    A Bob that, if the proper knowledge lands in his hands, is all too happy to perform decryption without Ursula.

    After all, Bob gonna Bob.
    """

    def __init__(self, session_seed=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class DKGOmniscientDecryptionClient(ThresholdDecryptionClient):
        def gather_encrypted_decryption_shares(
            self,
            encrypted_requests,
            threshold: int,
            timeout: float = 10,
        ) -> Tuple[
            Dict[ChecksumAddress, EncryptedThresholdDecryptionResponse],
            Dict[ChecksumAddress, str],
        ]:
            decryption_shares = {}

            ####################
            etdr = list(encrypted_requests.values())[0]

            #################

            for validator, validator_keypair in zip(
                self._learner._dkg_insight.validators,
                self._learner._dkg_insight.validator_keypairs,
            ):
                dkg = ferveo.Dkg(
                    tau=self._learner._dkg_insight.tau,
                    shares_num=self._learner._dkg_insight.shares_num,
                    security_threshold=self._learner._dkg_insight.security_threshold,
                    validators=self._learner._dkg_insight.validators,
                    me=validator,
                )

                # We can also obtain the aggregated transcript from the side-channel (deserialize)
                aggregate = ferveo.AggregatedTranscript(
                    self._learner._dkg_insight.aggregation_messages
                )
                assert aggregate.verify(
                    self._learner._dkg_insight.shares_num,
                    self._learner._dkg_insight.aggregation_messages,
                )

                trdp = (
                    self._learner._dkg_insight.fake_ritual.threshold_request_decrypting_power
                )
                decrypted_encryption_request = trdp.decrypt_encrypted_request(etdr)
                ciphertext = decrypted_encryption_request.ciphertext
                decryption_share = aggregate.create_decryption_share_simple(
                    dkg,
                    ciphertext,
                    self._learner._dkg_insight.conditions_bytes,
                    validator_keypair,
                )
                decryption_shares[validator.address] = decryption_share
                print(f"At share time: {self._learner._dkg_insight.dkg.public_key}")

                # Public key has changed because of transcript aggregation?
                self._learner._dkg_insight.dkg = dkg

            NO_FAILURES = {}
            return decryption_shares, NO_FAILURES

    _threshold_decryption_client_class = DKGOmniscientDecryptionClient

    def get_ritual_from_id(self, ritual_id):
        return self._dkg_insight.fake_ritual

    def resolve_cohort(self, ritual, timeout):
        return self._dkg_insight.fake_ritual.fake_nodes

    def ensure_ursula_availability_is_of_no_conern_to_anyone(self, *args, **kwargs):
        pass

    _ensure_ursula_availability = ensure_ursula_availability_is_of_no_conern_to_anyone

    # def threshold_decrypt(self, ciphertext, *args, **kwargs) -> bytes:
    #     """
    #     https://imgflip.com/i/7o0q5d  # Copilot gonns copilot
    #
    #     Cut Ursula out of the picture.
    #     """
    #     decryption_client = self._threshold_decryption_client_class(self)
    #     decryption_shares = decryption_client.gather_encrypted_decryption_shares(ciphertext)
    #
    #     shared_secret = ferveo.combine_decryption_shares_simple(decryption_shares)
    #
    #     print(f"Passing {self._dkg_insight.dkg.public_key} as the public key")
    #
    #     cleartext = ferveo.decrypt_with_shared_secret(
    #         ciphertext,
    #         self._dkg_insight.conditions_bytes,
    #         shared_secret,
    #         self._dkg_insight.dkg.public_params,
    #     )
    #     return bytes(cleartext)
