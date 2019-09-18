from twisted.internet import task
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.chaotic import Moe


class MoeBlockchainDataUtility:
    DEFAULT_REFRESH_RATE = 15  # every 15s

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
        agent = self._moe.staking_agent
        current_period = agent.get_current_period()

        nodes_dict = self._moe.known_nodes.abridged_nodes_dict()
        for checksum_address in nodes_dict:
            worker = agent.get_worker_from_staker(checksum_address)

            stake = agent.owned_tokens(checksum_address)
            staked_nu_tokens = float(NU.from_nunits(stake).to_tokens())
            locked_nu_tokens = float(NU.from_nunits(agent.get_locked_tokens(
                staker_address=checksum_address)).to_tokens())

            economics = TokenEconomicsFactory.get_economics(registry=self._moe.registry)
            stakes = StakeList(checksum_address=checksum_address, registry=self._moe.registry)
            stakes.refresh()
            start_date = datetime_at_period(current_period, seconds_per_period=economics.seconds_per_period)
            end_date = datetime_at_period(stakes.terminal_period, seconds_per_period=economics.seconds_per_period)

            last_confirmed_period = agent.get_last_active_period(checksum_address)

            print("==================================================")
            print(f"Checksum: {checksum_address}")
            print(f"Worker: {worker}")
            print(f"Start: {start_date}")
            print(f"End: {end_date}")
            print(f"Stake Value: {staked_nu_tokens}")
            print(f"Locked Stake: {locked_nu_tokens}")
            print(f"Current period: {current_period}")
            print(f"Last confirmed: {last_confirmed_period}")
            print("===================================================")

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f"Unhandled error: {cleaned_traceback}. Attempting to restart utility")
            if not self._learning_task.running:
                self.start()
        else:
            self.log.critical(f"Unhandled error: {cleaned_traceback}")

    def start(self):
        """
        Start the utility if not already running
        """
        if not self.is_running:
            self.log.info("Starting Moe Status Utility")
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
