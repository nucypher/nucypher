import sys
from operator import attrgetter
from typing import Dict, Tuple

from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    SessionSecretFactory,
    ThresholdDecryptionResponse,
    ferveo,
)

from nucypher.characters.lawful import Bob, Enrico
from nucypher.cli.types import ChecksumAddress
from nucypher.crypto.ferveo import dkg
from nucypher.crypto.powers import ThresholdRequestDecryptingPower
from nucypher.network.decryption import ThresholdDecryptionClient
from nucypher.network.middleware import RestMiddleware


class FakeNode:
    def __init__(self, checksum_address):
        self.checksum_address = checksum_address


class Uncoordinated:
    """
    A stand-in for some of the logic that is normally handled (and verified) by use of a Coordinator contract.
    """

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
        if session_seed is None:
            session_seed = b"ABytestringOf32BytesIsNeededHere"
        secret_factory = SessionSecretFactory.from_secure_randomness(session_seed)
        self.threshold_request_decrypting_power = ThresholdRequestDecryptingPower(
            session_secret_factory=secret_factory
        )
        # All participants have the same public key.
        fifty_fiver_public_key = (
            self.threshold_request_decrypting_power._get_static_secret_from_ritual_id(
                55
            ).public_key()
        )
        self.participant_public_keys = {
            checksum_address: fifty_fiver_public_key
            for checksum_address in checksum_addresses
        }


class DKGOmniscient:
    """
    A mixin to give a Character the ability to see the inner-workings of a DKG.
    """

    class DKGInsight:
        # TODO: Make these configurable:
        tau = 1  # ritual id
        security_threshold = 3
        shares_num = 4

        def __init__(self):
            """ """

            def gen_eth_addr(i: int) -> str:
                return f"0x{i:040x}"

            checksum_addresses = [gen_eth_addr(i) for i in range(0, self.shares_num)]

            self.fake_ritual = Uncoordinated(
                tau=self.tau,
                threshold=self.security_threshold,
                shares_num=self.shares_num,
                checksum_addresses=checksum_addresses,
            )

            validator_keypairs = [
                ferveo.Keypair.random() for _ in range(self.shares_num)
            ]

            validators = [
                ferveo.Validator(checksum_addresses[i], keypair.public_key())
                for i, keypair in enumerate(validator_keypairs)
            ]

            # Validators must be sorted by their public key
            validators.sort(key=attrgetter("address"))

            # Each validator generates a transcript which is publicly stored
            self.transcripts = []
            for sender in validators:
                transcript = dkg.generate_transcript(
                    ritual_id=self.tau,
                    me=sender,
                    shares=self.shares_num,
                    threshold=self.security_threshold,
                    nodes=validators,
                )
                self.transcripts.append((sender, transcript))

            self.dkg = dkg
            self.validators = validators
            self.validator_keypairs = validator_keypairs

            # any validator can generate the same aggregated transcript
            self.server_aggregate, self.dkg_public_key = dkg.aggregate_transcripts(
                ritual_id=self.tau,
                me=validators[0],
                shares=self.shares_num,
                threshold=self.security_threshold,
                transcripts=self.transcripts,
            )

    _dkg_insight = DKGInsight()


class NiceGuyEddie(Enrico, DKGOmniscient):
    """
    Like Enrico, but from Reservoir Dogs.

    He doesn't know who's shot, who's not.
    """

    def __init__(self, encrypting_key, *args, **kwargs):
        del encrypting_key  # We take this to match the Enrico public API, but we don't use it, because...

        # ...we're going to use the DKG public key as the encrypting key, and ignore the key passed in.
        encrypting_key_we_actually_want_to_use = self._dkg_insight.dkg_public_key
        super().__init__(
            # https://imgflip.com/i/7o0po4
            encrypting_key=encrypting_key_we_actually_want_to_use,
            *args,
            **kwargs,
        )


class DKGOmniscientDecryptionClient(ThresholdDecryptionClient):
    def gather_encrypted_decryption_shares(
        self,
        encrypted_requests: Dict[ChecksumAddress, EncryptedThresholdDecryptionRequest],
        threshold: int,
        timeout: int = ThresholdDecryptionClient.DEFAULT_DECRYPTION_TIMEOUT,
    ) -> Tuple[
        Dict[ChecksumAddress, EncryptedThresholdDecryptionResponse],
        Dict[ChecksumAddress, str],
    ]:
        # Set aside the power instance for use later, in the loop.
        trdp = self._learner._dkg_insight.fake_ritual.threshold_request_decrypting_power
        responses = {}

        # We only really need one encrypted tdr.
        etdr = list(encrypted_requests.values())[0]

        # decrypt request
        threshold_decryption_request = trdp.decrypt_encrypted_request(etdr)
        ciphertext_header = threshold_decryption_request.ciphertext_header
        acp = threshold_decryption_request.acp
        ritual_id = threshold_decryption_request.ritual_id
        variant = threshold_decryption_request.variant

        # We can obtain the transcripts from the side-channel (deserialize) and aggregate them
        validator_messages = [
            ferveo.ValidatorMessage(validator, transcript)
            for validator, transcript in self._learner._dkg_insight.transcripts
        ]
        aggregate = ferveo.AggregatedTranscript(validator_messages)
        assert aggregate.verify(
            self._learner._dkg_insight.shares_num,
            # TODO this list should not have to be passed again (either make `verify` static or use list
            #  provided in constructor
            validator_messages,
        )

        for validator, validator_keypair in zip(
            self._learner._dkg_insight.validators,
            self._learner._dkg_insight.validator_keypairs,
        ):
            # get decryption fragments/shares
            decryption_share = dkg.derive_decryption_share(
                ritual_id=ritual_id,
                me=validator,
                shares=self._learner._dkg_insight.shares_num,
                threshold=self._learner._dkg_insight.security_threshold,
                nodes=self._learner._dkg_insight.validators,
                aggregated_transcript=aggregate,
                keypair=validator_keypair,
                ciphertext_header=ciphertext_header,
                aad=acp.aad(),
                variant=variant,
            )

            decryption_response = ThresholdDecryptionResponse(
                ritual_id=55,  # TODO: Abstract this somewhere
                decryption_share=bytes(decryption_share),
            )

            encrypted_decryption_response = trdp.encrypt_decryption_response(
                decryption_response=decryption_response,
                requester_public_key=etdr.requester_public_key,
            )
            responses[validator.address] = encrypted_decryption_response

        NO_FAILURES = {}
        return responses, NO_FAILURES


class DoomedDecryptionClient(ThresholdDecryptionClient):
    """
    A decryption client that always fails, claiming that conditions are not satisfed.
    """

    def gather_encrypted_decryption_shares(
        self,
        encrypted_requests,
        threshold: int,
        timeout: int = ThresholdDecryptionClient.DEFAULT_DECRYPTION_TIMEOUT,
    ) -> Tuple[
        Dict[ChecksumAddress, EncryptedThresholdDecryptionResponse],
        Dict[ChecksumAddress, str],
    ]:
        NO_SUCCESSES = {}
        failures = {}

        for checksum_address in encrypted_requests:
            # Not really ideal, but we'll fake an exception here.
            # (to be forward-compatible with changes to Failure)
            # TODO: Dehydrate this logic in a single failure flow.
            try:
                raise RestMiddleware.Unauthorized("Decryption conditions not satisfied")
            except RestMiddleware.Unauthorized:
                failures[checksum_address] = sys.exc_info()

        return NO_SUCCESSES, failures


class _UpAndDownInTheWater(Bob, DKGOmniscient):
    """
    A Bob that, if the proper knowledge lands in his hands, is all too happy to perform decryption without Ursula.

    After all, Bob gonna Bob.
    """

    def __init__(self, session_seed=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_ritual_id_from_public_key(self, public_key) -> int:
        return 55  # any ritual id can be returned here

    def get_ritual(self, ritual_id):
        return self._dkg_insight.fake_ritual

    def resolve_cohort(self, ritual, timeout):
        return self._dkg_insight.fake_ritual.fake_nodes

    def ensure_ursula_availability_is_of_no_conern_to_anyone(self, *args, **kwargs):
        pass

    _ensure_ursula_availability = ensure_ursula_availability_is_of_no_conern_to_anyone


class ThisBobAlwaysDecrypts(_UpAndDownInTheWater):
    """
    A tool for testing success cases.
    """

    _threshold_decryption_client_class = DKGOmniscientDecryptionClient


class ThisBobAlwaysFails(_UpAndDownInTheWater):
    """
    A tool for testing interfaces which handle failures from conditions not having been met.
    """

    _threshold_decryption_client_class = DoomedDecryptionClient
