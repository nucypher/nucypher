from twisted.python.failure import Failure

from nucypher.blockchain.eth.agents import ContractAgency, TACoApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.task import SimpleTask


class OperatorBondedTracker(SimpleTask):
    INTERVAL = 60 * 60  # 1 hour

    class OperatorNoLongerBonded(RuntimeError):
        """Raised when a running node is no longer associated with a staking provider."""

    def __init__(self, ursula):
        self._ursula = ursula
        super().__init__()

    def run(self) -> None:
        application_agent = ContractAgency.get_agent(
            TACoApplicationAgent,
            registry=self._ursula.registry,
            blockchain_endpoint=self._ursula.eth_endpoint,
        )
        # use TACo root since unbonding happens at root and not child (more immediate this way)
        staking_provider_address = application_agent.get_staking_provider_from_operator(
            operator_address=self._ursula.operator_address
        )
        if staking_provider_address == NULL_ADDRESS:
            # forcibly shut down ursula
            self._shutdown_ursula(halt_reactor=True)

    def _shutdown_ursula(self, halt_reactor=False):
        emitter = StdoutEmitter()
        emitter.message(
            f"x [Operator {self._ursula.operator_address} is no longer bonded to any "
            f"staking provider] - Commencing auto-shutdown sequence...",
            color="red",
        )
        try:
            raise self.OperatorNoLongerBonded()
        finally:
            self._ursula.stop(halt_reactor=halt_reactor)

    def handle_errors(self, failure: Failure) -> None:
        cleaned_traceback = self.clean_traceback(failure)
        self.log.warn(
            f"Unhandled error during operator bonded check: {cleaned_traceback}"
        )
        if failure.check([self.OperatorNoLongerBonded]):
            # this type of exception we want to propagate because we will shut down
            failure.raiseException()
