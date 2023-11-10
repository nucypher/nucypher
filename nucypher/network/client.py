from typing import List

from eth_typing import ChecksumAddress

from nucypher.network.nodes import Learner
from nucypher.utilities.logging import Logger


class ThresholdAccessControlClient:
    """
    Client for communicating with access control nodes on the Threshold Network.
    """

    def __init__(self, learner: Learner):
        self._learner = learner
        self.log = Logger(self.__class__.__name__)

    def _ensure_ursula_availability(
        self, ursulas: List[ChecksumAddress], threshold: int, timeout: int
    ):
        """
        Make sure we know enough nodes;
        otherwise block and wait for them to come online.
        """

        # OK, so we're going to need to do some network activity for this retrieval.
        # Let's make sure we've seeded.
        if not self._learner.done_seeding:
            self._learner.learn_from_teacher_node()

        all_known_ursulas = self._learner.known_nodes.addresses()

        # Push all unknown Ursulas from the map in the queue for learning
        unknown_ursulas = ursulas - all_known_ursulas

        # If we know enough to decrypt, we can proceed.
        known_ursulas = ursulas & all_known_ursulas
        if len(known_ursulas) >= threshold:
            return

        # | <--- shares                                            ---> |
        # | <--- threshold               ---> | <--- allow_missing ---> |
        # | <--- known_ursulas ---> | <--- unknown_ursulas         ---> |
        allow_missing = len(ursulas) - threshold
        self._learner.block_until_specific_nodes_are_known(
            unknown_ursulas,
            timeout=timeout,
            allow_missing=allow_missing,
            learn_on_this_thread=True,
        )
