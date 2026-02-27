import math
from http import HTTPStatus
from typing import Dict, List, Tuple

from eth_typing import ChecksumAddress
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    EncryptedThresholdSignatureRequest,
    EncryptedThresholdSignatureResponse,
)

from nucypher.network.client import ThresholdAccessControlClient
from nucypher.utilities.concurrency import VariableBatchSizeValueFactory, WorkerPool


class NetworkRequestClient(ThresholdAccessControlClient):
    DEFAULT_TIMEOUT = 30
    DEFAULT_STAGGER_TIMEOUT = 3
    DEFAULT_MAX_WORKER_THREADS_PER_REQUEST = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class RequestFactory(VariableBatchSizeValueFactory):
        """
        A ValueFactory for WorkerPool that allows us to specify a dynamic batch size based
        on the number of successes so far.
        """

        """
        :param ursulas_to_contact: The list of ursula addresses to contact.
        :param threshold: The number of successful responses required to meet the threshold for this request.
        :param threshold_batch_buffer_factor: A multiplier to add extra buffer to the batch size of nodes contacted in addition to the the threshold.
        """
        def __init__(
            self,
            ursulas_to_contact: List[ChecksumAddress],
            threshold: int,
            threshold_batch_buffer_factor: float = 0.25,
        ):
            super().__init__(
                values=ursulas_to_contact,
                required_successes=threshold,
            )

            if threshold_batch_buffer_factor is None or not (
                0 <= threshold_batch_buffer_factor <= 1.0
            ):
                raise ValueError(
                    "Threshold batch buffer factor must be between 0 and 1"
                )

            self._required_successes_plus_buffer = math.ceil(
                threshold * (1 + threshold_batch_buffer_factor)
            )

        def get_custom_batch_size(self, successes) -> int:
            if self.required_successes <= successes:
                # should never get here since the WorkerPool should stop once we have enough successes
                raise ValueError(
                    "Current successes cannot be greater than or equal to the threshold"
                )

            additional_successes_needed = (
                self._required_successes_plus_buffer - successes
            )
            return additional_successes_needed

    def execute(
        self,
        requests: Dict,
        worker,
        threshold: int,
        timeout: int,
        stagger_timeout: int = DEFAULT_STAGGER_TIMEOUT,
    ) -> Tuple[Dict, Dict]:

        ursulas_to_contact = (
            self._learner.node_latency_collector.order_addresses_by_latency(
                list(requests)
            )
            if self._learner.node_latency_collector
            else list(requests)
        )

        # Discussion about WorkerPool parameters:
        # "https://github.com/nucypher/nucypher/pull/3393#discussion_r1456307991"
        worker_pool = WorkerPool(
            worker=worker,
            value_factory=self.RequestFactory(
                ursulas_to_contact=ursulas_to_contact,
                threshold=threshold,
            ),
            target_successes=threshold,
            threadpool_size=min(
                self.DEFAULT_MAX_WORKER_THREADS_PER_REQUEST, math.ceil(threshold * 1.5)
            ),
            timeout=timeout,
            stagger_timeout=stagger_timeout,
        )
        worker_pool.start()
        try:
            successes = worker_pool.block_until_target_successes()
        except (WorkerPool.OutOfValues, WorkerPool.TimedOut):
            # It's possible to raise some other exceptions here but we will use the logic below.
            successes = worker_pool.get_successes()
        finally:
            worker_pool.cancel()

        failures = worker_pool.get_failures()
        if len(successes) < threshold:
            # threshold not met and some ursulas did not respond at all; mark them as timeout failures
            for ursula in ursulas_to_contact:
                if ursula not in successes and ursula not in failures:
                    failures[ursula] = (
                        f"Node {ursula} did not respond before timeout ({timeout}s)."
                    )

        return successes, failures


class ThresholdDecryptionClient(NetworkRequestClient):

    class ThresholdDecryptionRequestFailed(Exception):
        """Raised when a decryption request returns a non-zero status code."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def gather_encrypted_decryption_shares(
        self,
        encrypted_requests: Dict[ChecksumAddress, EncryptedThresholdDecryptionRequest],
        threshold: int,
        timeout: int = NetworkRequestClient.DEFAULT_TIMEOUT,
        stagger_timeout: int = NetworkRequestClient.DEFAULT_STAGGER_TIMEOUT,
    ) -> Tuple[
        Dict[ChecksumAddress, EncryptedThresholdDecryptionResponse],
        Dict[ChecksumAddress, str],
    ]:
        self._ensure_ursula_availability(
            ursulas=list(encrypted_requests.keys()),
            threshold=threshold,
            timeout=timeout,  # TODO this was 60s (peering timeout) before
        )

        def worker(
            ursula_address: ChecksumAddress,
        ) -> EncryptedThresholdDecryptionResponse:

            encrypted_request = encrypted_requests[ursula_address]

            try:
                node_or_sprout = self._learner.known_nodes[ursula_address]
                node_or_sprout.mature()
                response = (
                    self._learner.network_middleware.get_encrypted_decryption_share(
                        ursula=node_or_sprout,
                        decryption_request_bytes=bytes(encrypted_request),
                        timeout=timeout,
                    )
                )
                if response.status_code == HTTPStatus.OK:
                    return EncryptedThresholdDecryptionResponse.from_bytes(
                        response.content
                    )
            except Exception as e:
                message = f"Node {ursula_address} raised {e}"
                self.log.warn(message)
                raise self.ThresholdDecryptionRequestFailed(message)

            message = f"Node {ursula_address} returned {response.status_code} - {response.content}."
            self.log.warn(message)
            raise self.ThresholdDecryptionRequestFailed(message)

        successes, failures = self.execute(
            requests=encrypted_requests,
            worker=worker,
            threshold=threshold,
            timeout=timeout,
            stagger_timeout=stagger_timeout,
        )

        return successes, failures


class SigningRequestClient(NetworkRequestClient):

    class SigningRequestFailed(Exception):
        """Raised when a signing request returns a non-zero status code."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def gather_signatures(
        self,
        encrypted_requests: Dict[
            ChecksumAddress,
            EncryptedThresholdSignatureRequest,
        ],
        threshold: int,
        timeout: int = NetworkRequestClient.DEFAULT_TIMEOUT,
        stagger_timeout: int = NetworkRequestClient.DEFAULT_STAGGER_TIMEOUT,
    ) -> Tuple[
        Dict[ChecksumAddress, EncryptedThresholdSignatureResponse],
        Dict[ChecksumAddress, str],
    ]:
        self._ensure_ursula_availability(
            ursulas=list(encrypted_requests.keys()),
            threshold=threshold,
            timeout=timeout,  # TODO this was 60s (peering timeout) before
        )

        def worker(
            ursula_address: ChecksumAddress,
        ) -> EncryptedThresholdSignatureResponse:

            encrypted_request = encrypted_requests[ursula_address]

            try:
                node_or_sprout = self._learner.known_nodes[ursula_address]
                node_or_sprout.mature()
                response = self._learner.network_middleware.request_signature(
                    ursula=node_or_sprout,
                    signing_request_bytes=bytes(encrypted_request),
                    timeout=timeout,
                )
                if response.status_code == HTTPStatus.OK:
                    signature_response = EncryptedThresholdSignatureResponse.from_bytes(
                        response.content
                    )
                    return signature_response

            except Exception as e:
                message = f"Node {ursula_address} raised {e}"
                self.log.warn(message)
                raise self.SigningRequestFailed(message)

            message = f"Node {ursula_address} returned {response.status_code} - {response.content}."
            self.log.warn(message)
            raise self.SigningRequestFailed(message)

        successes, failures = self.execute(
            requests=encrypted_requests,
            worker=worker,
            threshold=threshold,
            timeout=timeout,
            stagger_timeout=stagger_timeout,
        )

        return successes, failures
