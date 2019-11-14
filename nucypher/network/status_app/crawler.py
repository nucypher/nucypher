from pendulum.parsing import ParserError
from twisted.internet import task
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.chaotic import Moe
from influxdb import InfluxDBClient
from maya import MayaDT

from nucypher.network.status_app.db import InfluxCrawlerClient
import sqlite3
import os


class NetworkCrawler:
    """
    Obtain Blockchain information for Moe and output to a DB.
    """
    DEFAULT_REFRESH_RATE = 60  # seconds

    # InfluxDB Line Protocol Format (note the spaces, commas):
    # +-----------+--------+-+---------+-+---------+
    # |measurement|,tag_set| |field_set| |timestamp|
    # +-----------+--------+-+---------+-+---------+
    BLOCKCHAIN_DB_MEASUREMENT = 'moe_network_info'
    BLOCKCHAIN_DB_LINE_PROTOCOL = '{measurement},staker_address={staker_address} ' \
                           'worker_address="{worker_address}",' \
                           'start_date={start_date},' \
                           'end_date={end_date},' \
                           'stake={stake},' \
                           'locked_stake={locked_stake},' \
                           'current_period={current_period}i,' \
                           'last_confirmed_period={last_confirmed_period}i ' \
                       '{timestamp}'
    BLOCKCHAIN_DB_NAME = 'network'

    BLOCKCHAIN_DB_RETENTION_POLICY_NAME = 'network_info_retention'
    BLOCKCHAIN_DB_RETENTION_POLICY_PERIOD = '5w'  # 5 weeks of data
    BLOCKCHAIN_DB_RETENTION_POLICY_REPLICATION = '1'

    # SQLlite3 constants
    NODES_DB_NAME = 'nodes'
    FUTURE_TOKENS_DB_NAME = 'future_locked_tokens'
    MOE_DB_FILE = '/tmp/moe_data.db'

    def __init__(self,
                 moe: Moe,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True):

        self._moe = moe
        self._refresh_rate = refresh_rate
        self._nodes_contract_info_learning_task = task.LoopingCall(self._learn_about_nodes_contract_info)
        self._locked_tokens_learning_task = task.LoopingCall(self._learn_about_locked_tokens)
        self._moe_known_nodes_learning_task = task.LoopingCall(self._learn_about_moe_known_nodes)
        self._restart_on_error = restart_on_error
        self.log = Logger('moe-crawler')

        # initialize InfluxDB for Blockchain information
        self._blockchain_db_client = InfluxDBClient(host='localhost', port=8086, database=self.BLOCKCHAIN_DB_NAME)
        self._ensure_blockchain_db_exists()

        # initialize SQLite3 for Node information
        if os.path.exists(self.MOE_DB_FILE):
            # ensure empty db to start
            os.remove(self.MOE_DB_FILE)
        self._nodes_db_client = sqlite3.connect(self.MOE_DB_FILE)
        self._create_nodes_db_table()

    def _ensure_blockchain_db_exists(self):
        db_list = self._blockchain_db_client.get_list_database()
        found_db = (list(filter(lambda db: db['name'] == self.BLOCKCHAIN_DB_NAME, db_list)))
        if len(found_db) == 0:
            # db not previously created
            self.log.info(f'Database {self.BLOCKCHAIN_DB_NAME} not found, creating it')
            self._blockchain_db_client.create_database(self.BLOCKCHAIN_DB_NAME)
            # TODO: review defaults for retention policy
            self._blockchain_db_client.create_retention_policy(name=self.BLOCKCHAIN_DB_RETENTION_POLICY_NAME,
                                                               duration=self.BLOCKCHAIN_DB_RETENTION_POLICY_PERIOD,
                                                               replication=self.BLOCKCHAIN_DB_RETENTION_POLICY_REPLICATION,
                                                               database=self.BLOCKCHAIN_DB_NAME,
                                                               default=True)
        else:
            self.log.info(f'Database {self.BLOCKCHAIN_DB_NAME} already exists, no need to create it')

    def _create_nodes_db_table(self):
        # staker_address, nickname, status_message, timestamp, last_seen, fleet_state_icon, is_teacher
        with self._nodes_db_client:
            self._nodes_db_client.execute(f"CREATE TABLE {self.NODES_DB_NAME} (staker_address text primary key, "
                                          f"nickname text, status_message text, timestamp date, last_seen text, "
                                          f"fleet_state text, is_teacher text)")

            self._nodes_db_client.execute(f"CREATE TABLE {self.FUTURE_TOKENS_DB_NAME} (day integer primary key, "
                                          f"tokens integer)")

    def _learn_about_locked_tokens(self):
        period_range = range(1, 365+1)
        token_counter = [(day,  int(NU.from_nunits(self._moe.staking_agent.get_all_locked_tokens(day)).to_tokens()))
                         for day in period_range]

        with self._nodes_db_client:
            self._nodes_db_client.executemany(f'REPLACE INTO {self.FUTURE_TOKENS_DB_NAME} VALUES(?,?)',
                                              token_counter)

    def _learn_about_nodes_contract_info(self):
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
            start_date = datetime_at_period(stakes.initial_period,
                                            seconds_per_period=economics.seconds_per_period).datetime().timestamp()
            end_date = datetime_at_period(stakes.terminal_period,
                                          seconds_per_period=economics.seconds_per_period).datetime().timestamp()

            last_confirmed_period = agent.get_last_active_period(staker_address)

            # TODO: do we need to worry about how much information is in memory if number of nodes is
            #  large i.e. should I check for size of data and write within loop if too big
            data.append(self.BLOCKCHAIN_DB_LINE_PROTOCOL.format(
                measurement=self.BLOCKCHAIN_DB_MEASUREMENT,
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

        if not self._blockchain_db_client.write_points(data,
                                                       database=self.BLOCKCHAIN_DB_NAME,
                                                       time_precision='s',
                                                       batch_size=10000,
                                                       protocol='line'):
            # TODO: what do we do here
            self.log.warn(f'Unable to write to database {self.BLOCKCHAIN_DB_NAME} at '
                          f'{MayaDT(epoch=block_time)} | Period {current_period}')

    def _learn_about_moe_known_nodes(self):
        nodes_dict = self._moe.known_nodes.abridged_nodes_dict()
        teacher_node_checksum = self._moe.current_teacher_node().checksum_address
        current_period = self._moe.staking_agent.get_current_period()

        db_rows = []
        checksum_addresses = list(nodes_dict.keys())
        for checksum in checksum_addresses:
            node_data = nodes_dict[checksum]
            db_rows.append(self.get_node_db_row_information(node_data, teacher_node_checksum, current_period))

        with self._nodes_db_client:
            self._nodes_db_client.executemany(f'REPLACE INTO {self.NODES_DB_NAME} VALUES(?,?,?,?,?,?,?)', db_rows)

    def _handle_errors(self, *args, **kwargs):
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        if self._restart_on_error:
            self.log.warn(f'Unhandled error: {cleaned_traceback}. Attempting to restart crawler')
            if not self._nodes_contract_info_learning_task.running:
                self.start()
        else:
            self.log.critical(f'Unhandled error: {cleaned_traceback}')

    def start(self):
        """
        Start the crawler if not already running
        """
        if not self.is_running:
            self.log.info('Starting Moe Crawler')
            if self._blockchain_db_client is None:
                self._blockchain_db_client = InfluxDBClient(host='localhost',
                                                            port=8086,
                                                            database=self.BLOCKCHAIN_DB_NAME)

            if self._nodes_db_client is None:
                self._nodes_db_client = sqlite3.connect(self.MOE_DB_FILE)

            # start tasks
            node_learner_deferred = self._nodes_contract_info_learning_task.start(interval=self._refresh_rate, now=True)
            contract_learner_deferred = self._locked_tokens_learning_task.start(interval=self._refresh_rate, now=True)
            moe_nodes_deferred = self._moe_known_nodes_learning_task.start(interval=self._refresh_rate, now=True)

            # hookup error callbacks
            node_learner_deferred.addErrback(self._handle_errors)
            contract_learner_deferred.addErrback(self._handle_errors)
            moe_nodes_deferred.addErrback(self._handle_errors)

    def stop(self):
        """
        Stop the crawler if currently running
        """
        if self.is_running:
            self.log.info('Stopping Moe Crawler')

            # stop tasks
            self._nodes_contract_info_learning_task.stop()
            self._locked_tokens_learning_task.stop()
            self._moe_known_nodes_learning_task.stop()

            # close connections
            self._blockchain_db_client.close()
            self._blockchain_db_client = None
            self._nodes_db_client.close()
            self._nodes_db_client = None

    @property
    def is_running(self):
        """
        Returns True if currently running, False otherwise
        :return: True if currently running, False otherwise
        """
        return (self._nodes_contract_info_learning_task.running
                and self._locked_tokens_learning_task.running
                and self._moe_known_nodes_learning_task.running)

    def get_blockchain_crawler_client(self):
        return InfluxCrawlerClient(host='localhost', port=8086, database=self.BLOCKCHAIN_DB_NAME)

    def get_node_db_row_information(self, node_info, teacher_address, current_period):
        # Staker address
        staker_address = node_info['staker_address']

        # Teacher?
        is_teacher = False
        if staker_address == teacher_address:
            is_teacher = True

        # Status info
        last_confirmed_period = self._moe.staking_agent.get_last_active_period(staker_address)
        status_message = self.get_node_status_message(staker_address, last_confirmed_period, current_period)

        # Nickname
        nickname = node_info['nickname']

        # Timestamp
        timestamp = node_info['timestamp']

        try:
            slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
        except ParserError:
            slang_last_seen = node_info['last_seen']
        last_seen = f"{slang_last_seen} | Period {last_confirmed_period}"

        fleet_state_icon = node_info['fleet_state_icon']

        return staker_address, nickname, status_message, timestamp, last_seen, fleet_state_icon, str(is_teacher)

    def get_node_status_message(self, staker_address, last_confirmed_period, current_period):
        missing_confirmations = current_period - last_confirmed_period
        worker = self._moe.staking_agent.get_worker_from_staker(staker_address)
        if worker == BlockchainInterface.NULL_ADDRESS:
            missing_confirmations = BlockchainInterface.NULL_ADDRESS

        status_codex = {
            -1: 'OK',  # Confirmed Next Period
            0: 'Pending',  # Pending Confirmation of Next Period
            current_period: 'Idle',  # Never confirmed
            BlockchainInterface.NULL_ADDRESS: 'Headless'  # Headless Staker (No Worker)
        }

        try:
            status_message = status_codex[missing_confirmations]
        except KeyError:
            status_message = f'{missing_confirmations} Unconfirmed'

        return status_message
