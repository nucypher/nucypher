import math
from http import HTTPStatus
from random import shuffle
from typing import Dict, List, Tuple

from eth_typing import ChecksumAddress
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
)

from nucypher.network.client import ThresholdAccessControlClient
from nucypher.utilities.concurrency import BatchValueFactory, WorkerPool


class ThresholdDecryptionClient(ThresholdAccessControlClient):
    DEFAULT_DECRYPTION_TIMEOUT = 30
    DEFAULT_STAGGER_TIMEOUT = 3

    class ThresholdDecryptionRequestFailed(Exception):
        """Raised when a decryption request returns a non-zero status code."""

    class ThresholdDecryptionRequestFactory(BatchValueFactory):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def gather_encrypted_decryption_shares(
        self,
        encrypted_requests: Dict[ChecksumAddress, EncryptedThresholdDecryptionRequest],
        threshold: int,
        timeout: int = DEFAULT_DECRYPTION_TIMEOUT,
        stagger_timeout: int = DEFAULT_STAGGER_TIMEOUT,
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

        # TODO: Find a better request order, perhaps based on latency data obtained from discovery loop - #3395
        requests = list(encrypted_requests)
        shuffle(requests)
        # Discussion about WorkerPool parameters:
        # "https://github.com/nucypher/nucypher/pull/3393#discussion_r1456307991"
        worker_pool = WorkerPool(
            worker=worker,
            value_factory=self.ThresholdDecryptionRequestFactory(
                ursulas_to_contact=requests,
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
