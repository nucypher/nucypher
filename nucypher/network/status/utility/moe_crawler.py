from datetime import datetime, timedelta
from typing import Dict, List

from twisted.internet import task
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.chaotic import Moe
from influxdb import InfluxDBClient
from maya import MayaDT


class MoeBlockchainCrawler:
    """
    Obtain Blockchain information for Moe and output to a DB
    """
    DEFAULT_REFRESH_RATE = 15  # every 15s

    # InfluxDB Line Protocol Format (note the spaces, commas):
    # +-----------+--------+-+---------+-+---------+
    # |measurement|,tag_set| |field_set| |timestamp|
    # +-----------+--------+-+---------+-+---------+
    MEASUREMENT = 'moe_network_info'
    LINE_PROTOCOL = '{measurement},staker_address={staker_address} ' \
                        'worker_address="{worker_address}",' \
                        'start_date={start_date},' \
                        'end_date={end_date},' \
                        'stake={stake},' \
                        'locked_stake={locked_stake},' \
                        'current_period={current_period}i,' \
                        'last_confirmed_period={last_confirmed_period}i ' \
                    '{timestamp}'
    DB_NAME = 'network'
    RETENTION_POLICY = 'network_info_retention'

    def __init__(self,
                 moe: Moe,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True):
        if not moe:
            raise ValueError('Moe must be provided')
        self._moe = moe
        self._refresh_rate = refresh_rate
        self._learning_task = task.LoopingCall(self._learn_about_network)
        self._restart_on_error = restart_on_error
        self.log = Logger('moe-crawler')

        # initialize InfluxDB
        self._client = InfluxDBClient(host='localhost', port=8086, database=self.DB_NAME)
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        db_list = self._client.get_list_database()
        found_db = (list(filter(lambda db: db['name'] == self.DB_NAME, db_list)))
        if len(found_db) == 0:
            # db not previously created
            self.log.info(f'Database {self.DB_NAME} not found, creating it')
            self._client.create_database(self.DB_NAME)
            # TODO: review defaults for retention policy
            self._client.create_retention_policy(name=self.RETENTION_POLICY,
                                                 duration='1w',
                                                 replication='1',
                                                 database=self.DB_NAME,
                                                 default=True)
        else:
            self.log.info(f'Database {self.DB_NAME} already exists, no need to create it')

    def _learn_about_network(self):
        agent = self._moe.staking_agent

        block_time = agent.blockchain.client.w3.eth.getBlock('latest').timestamp  # precision in seconds
        current_period = agent.get_current_period()

        nodes_dict = self._moe.known_nodes.abridged_nodes_dict()
        self.log.info(f'Processing {len(nodes_dict)} nodes at '
                      f'{MayaDT(epoch=block_time)} | Period {current_period}')
        data = []
        for staker_address in nodes_dict:
            worker = agent.get_worker_from_staker(staker_address)

            stake = agent.owned_tokens(staker_address)
            staked_nu_tokens = float(NU.from_nunits(stake).to_tokens())
            locked_nu_tokens = float(NU.from_nunits(agent.get_locked_tokens(
                staker_address=staker_address)).to_tokens())

            economics = TokenEconomicsFactory.get_economics(registry=self._moe.registry)
            stakes = StakeList(checksum_address=staker_address, registry=self._moe.registry)
            stakes.refresh()

            # store dates as floats for comparison purposes
            start_date = datetime_at_period(current_period,
                                            seconds_per_period=economics.seconds_per_period).datetime().timestamp()
            end_date = datetime_at_period(stakes.terminal_period,
                                          seconds_per_period=economics.seconds_per_period).datetime().timestamp()

            last_confirmed_period = agent.get_last_active_period(staker_address)

            # TODO: do we need to worry about how much information is in memory if number of nodes is
            #  large i.e. should I check for size of data and write within loop if too big
            data.append(self.LINE_PROTOCOL.format(
                measurement=self.MEASUREMENT,
                staker_address=staker_address,
                worker_address=worker,
                start_date=start_date,
                end_date=end_date,
                stake=staked_nu_tokens,
                locked_stake=locked_nu_tokens,
                current_period=current_period,
                last_confirmed_period=last_confirmed_period,
                timestamp=block_time
            ))

        if not self._client.write_points(data,
                                         database=self.DB_NAME,
                                         time_precision='s',
                                         batch_size=10000,
                                         protocol='line'):
            # TODO: what do we do here
            self.log.warn(f'Unable to write to database {self.DB_NAME} at '
                          f'{MayaDT(epoch=block_time)} | Period {current_period}')

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f'Unhandled error: {cleaned_traceback}. Attempting to restart crawler')
            if not self._learning_task.running:
                self.start()
        else:
            self.log.critical(f'Unhandled error: {cleaned_traceback}')

    def start(self):
        """
        Start the crawler if not already running
        """
        if not self.is_running:
            self.log.info('Starting Moe Crawler')
            learner_deferred = self._learning_task.start(interval=self._refresh_rate, now=True)
            learner_deferred.addErrback(self._handle_errors)

    def stop(self):
        """
        Stop the crawler if currently running
        """
        if not self.is_running:
            self.log.info('Stopping Moe Crawler')
            self._learning_task.stop()

    @property
    def is_running(self):
        """
        Returns True if currently running, False otherwise
        :return: True if currently running, False otherwise
        """
        return self._learning_task.running

    def get_db_client(self):
        return MoeCrawlerDBClient(host='localhost', port=8086, database=self.DB_NAME)


class MoeCrawlerDBClient:
    def __init__(self, host, port, database):
        self._client = InfluxDBClient(host=host, port=port, database=database)

    def get_future_locked_tokens_over_day_range(self, days: int) -> Dict[int, float]:
        tomorrow = datetime.utcnow() + timedelta(days=1)
        period_0 = datetime(year=tomorrow.year, month=tomorrow.month,
                            day=tomorrow.day, hour=0, minute=0, second=0, microsecond=0)

        node_data = list(self._client.query("SELECT staker_address, start_date, end_date, LAST(locked_stake) as "
                                            "locked_stake from moe_network_info GROUP BY staker_address").get_points())
        result = dict()
        day_range = list(range(1, days + 1))
        current_period = period_0
        for day in day_range:
            current_period = current_period + timedelta(days=1)
            total_locked_tokens = 0
            for node_dict in node_data:
                start_date = datetime.utcfromtimestamp(node_dict['start_date'])
                end_date = datetime.utcfromtimestamp(node_dict['end_date'])

                if start_date <= current_period <= end_date:
                    total_locked_tokens += node_dict['locked_stake']

            result[day] = total_locked_tokens

        return result
