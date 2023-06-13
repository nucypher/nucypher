import json
from typing import Dict, Tuple

from nucypher_core import EncryptedThresholdDecryptionResponse, ferveo

from nucypher.characters.lawful import Bob, Enrico
from nucypher.cli.types import ChecksumAddress
from nucypher.network.decryption import ThresholdDecryptionClient
from nucypher.policy.conditions.types import LingoList
from nucypher.policy.conditions.utils import validate_condition_lingo


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

    class DKGOmniscientDecryptionClient(ThresholdDecryptionClient):
        def gather_encrypted_decryption_shares(
            self,
            *args,
            **kwargs,
        ) -> Tuple[
            Dict[ChecksumAddress, EncryptedThresholdDecryptionResponse],
            Dict[ChecksumAddress, str],
        ]:
            assert (
                False  # This is where DKGomniscent just knows the shares in question.
            )

    _threshold_decryption_client_class = DKGOmniscientDecryptionClient

    @property
    def done_seeding(self, *args, **kwargs):
        return True

    @done_seeding.setter
    def done_seeding(self, *args, **kwargs):
        return True  # We were done seeding before we started.

    def ensure_ursula_availability_is_of_no_conern_to_anyone(self, *args, **kwargs):
        pass

    _ensure_ursula_availability = ensure_ursula_availability_is_of_no_conern_to_anyone

    def threshold_decrypt(self, ciphertext, *args, **kwargs) -> bytes:
        """
        https://imgflip.com/i/7o0q5d  # Copilot gonns copilot

        Cut Ursula out of the picture.
        """
        decryption_shares = []
        for validator, validator_keypair in zip(
            self._dkg_insight.validators, self._dkg_insight.validator_keypairs
        ):
            dkg = ferveo.Dkg(
                tau=self._dkg_insight.tau,
                shares_num=self._dkg_insight.shares_num,
                security_threshold=self._dkg_insight.security_threshold,
                validators=self._dkg_insight.validators,
                me=validator,
            )

            # We can also obtain the aggregated transcript from the side-channel (deserialize)
            aggregate = ferveo.AggregatedTranscript(
                self._dkg_insight.aggregation_messages
            )
            assert aggregate.verify(
                self._dkg_insight.shares_num, self._dkg_insight.aggregation_messages
            )

            # We can also obtain the aggregated transcript from the side-channel (deserialize)
            aggregate = ferveo.AggregatedTranscript(
                self._dkg_insight.aggregation_messages
            )
            assert aggregate.verify(
                self._dkg_insight.shares_num, self._dkg_insight.aggregation_messages
            )

            # Create a decryption share for the ciphertext
            decryption_share = aggregate.create_decryption_share_simple(
                dkg, ciphertext, self._dkg_insight.conditions_bytes, validator_keypair
            )
            decryption_shares.append(decryption_share)
        shared_secret = ferveo.combine_decryption_shares_simple(decryption_shares)

        cleartext = ferveo.decrypt_with_shared_secret(
            ciphertext,
            self._dkg_insight.conditions_bytes,
            shared_secret,
            self._dkg_insight.dkg.public_params,
        )
        return bytes(cleartext)
