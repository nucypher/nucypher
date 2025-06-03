import math
from collections import OrderedDict
from http import HTTPStatus
from typing import Dict, List, Tuple

from eth_typing import ChecksumAddress
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
)

from nucypher.network.client import ThresholdAccessControlClient
from nucypher.network.signing import BaseSignatureRequest, SignatureResponse
from nucypher.utilities.concurrency import BatchValueFactory, WorkerPool


class NetworkRequestClient(ThresholdAccessControlClient):
    DEFAULT_TIMEOUT = 30
    DEFAULT_STAGGER_TIMEOUT = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class RequestFactory(BatchValueFactory):
        def __init__(
            self,
            ursulas_to_contact: List[ChecksumAddress],
            threshold: int,
            batch_size: int,
        ):
            super().__init__(
                values=ursulas_to_contact,
                required_successes=threshold,
                batch_size=batch_size,
            )

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
                batch_size=math.ceil(threshold * 1.25),
                threshold=threshold,
            ),
            target_successes=threshold,
            threadpool_size=math.ceil(
                threshold * 1.5
            ),  # TODO should we cap this (say 40?)
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
        signing_requests: Dict[ChecksumAddress, BaseSignatureRequest],
        threshold: int,
        timeout: int = NetworkRequestClient.DEFAULT_TIMEOUT,
        stagger_timeout: int = NetworkRequestClient.DEFAULT_STAGGER_TIMEOUT,
    ) -> Tuple[
        Dict[ChecksumAddress, Tuple[ChecksumAddress, SignatureResponse]],
        Dict[ChecksumAddress, str],
    ]:
        self._ensure_ursula_availability(
            ursulas=list(signing_requests.keys()),
            threshold=threshold,
            timeout=timeout,  # TODO this was 60s (peering timeout) before
        )

        def worker(
            ursula_address: ChecksumAddress,
        ) -> Tuple[ChecksumAddress, SignatureResponse]:

            encrypted_request = signing_requests[ursula_address]

            try:
                node_or_sprout = self._learner.known_nodes[ursula_address]
                node_or_sprout.mature()
                response = self._learner.network_middleware.request_signature(
                    ursula=node_or_sprout,
                    signing_request_bytes=bytes(encrypted_request),
                    timeout=timeout,
                )
                if response.status_code == HTTPStatus.OK:
                    response = SignatureResponse.from_bytes(response.content)
                    operator_address = node_or_sprout.operator_address
                    return operator_address, response

            except Exception as e:
                message = f"Node {ursula_address} raised {e}"
                self.log.warn(message)
                raise self.SigningRequestFailed(message)

            message = f"Node {ursula_address} returned {response.status_code} - {response.content}."
            self.log.warn(message)
            raise self.SigningRequestFailed(message)

        successes, failures = self.execute(
            requests=signing_requests,
            worker=worker,
            threshold=threshold,
            timeout=timeout,
            stagger_timeout=stagger_timeout,
        )

        # sort successes by operator address
        # successes is of type Dict[ChecksumAddress, Tuple[ChecksumAddress, ThresholdSignatureResponse]]
        successes = OrderedDict(sorted(successes.items(), key=lambda item: item[1][0]))

        return successes, failures
