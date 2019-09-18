from nucypher.characters.chaotic import Moe
from twisted.internet import task
from twisted.logger import Logger


class MoeBlockchainDataUtility:
    DEFAULT_REFRESH_RATE = 15  # every 15s
    DB_FILE = "file"
    DB_NAME = 'name'

    def __init__(self,
                 moe: Moe,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True):
        if not moe:
            raise ValueError("Moe must be provided")
        self._moe = moe
        self._refresh_rate = refresh_rate
        self._learning_task = task.LoopingCall(self._learn_about_network)
        self._restart_on_error = restart_on_error
        self.log = Logger("moe-data-utility")

    def _learn_about_network(self):
        pass

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f"Unhandled error during crawling: {cleaned_traceback}. Attempting to restart crawler")
            if not self._learning_task.running:
                self.start()
        else:
            self.log.critical(f"Unhandled error during crawling: {cleaned_traceback}")

    def start(self):
        """
        Start the utility if not already running
        """
        if not self.is_running:
            self.log("Starting Moe Status Crawler")
            learner_deferred = self._learning_task.start(interval=self._refresh_rate, now=True)
            learner_deferred.addErrback(self._handle_errors)

    def stop(self):
        """
        Stop the utility if currently running
        """
        if not self.is_running:
            self._learning_task.stop()

    @property
    def is_running(self):
        """
        Returns True if currently running, False otherwise
        :return: True if currently running, False otherwise
        """
        return self._learning_task.running
