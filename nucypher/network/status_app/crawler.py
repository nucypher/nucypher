from influxdb import InfluxDBClient
from maya import MayaDT
from twisted.internet import task
from twisted.logger import Logger

from nucypher.blockchain.economics import TokenEconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, NucypherTokenAgent, PolicyManagerAgent, \
    AdjudicatorAgent
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.network.nodes import Learner
from nucypher.network.status_app.db import BlockchainCrawlerClient


class NetworkCrawler(Learner):
    """
    Obtain Blockchain information for Moe and output to a DB.
    """

    _SHORT_LEARNING_DELAY = .5
    _LONG_LEARNING_DELAY = 30
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

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

    def __init__(self,
                 registry,
                 federated_only: bool = False,
                 refresh_rate=DEFAULT_REFRESH_RATE,
                 restart_on_error=True,
                 *args, **kwargs):

        self.registry = registry
        self.federated_only = federated_only
        super().__init__(*args, **kwargs)
        self.log = Logger('network-crawler')

        self._refresh_rate = refresh_rate
        self._restart_on_error = restart_on_error

        # Agency
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=self.registry)
        self.policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=self.registry)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

        # Crawler Tasks
        self._nodes_contract_info_learning_task = task.LoopingCall(self._learn_about_nodes_contract_info)

        # initialize InfluxDB for Blockchain information
        self._blockchain_db_client = InfluxDBClient(host='localhost', port=8086, database=self.BLOCKCHAIN_DB_NAME)
        self._ensure_blockchain_db_exists()

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

    def _learn_about_nodes_contract_info(self):
        agent = self.staking_agent

        block_time = agent.blockchain.client.w3.eth.getBlock('latest').timestamp  # precision in seconds
        current_period = agent.get_current_period()

        nodes_dict = self.known_nodes.abridged_nodes_dict()
        self.log.info(f'Processing {len(nodes_dict)} nodes at '
                      f'{MayaDT(epoch=block_time)} | Period {current_period}')
        data = []
        for staker_address in nodes_dict:
            worker = agent.get_worker_from_staker(staker_address)

            stake = agent.owned_tokens(staker_address)
            staked_nu_tokens = float(NU.from_nunits(stake).to_tokens())
            locked_nu_tokens = float(NU.from_nunits(agent.get_locked_tokens(
                staker_address=staker_address)).to_tokens())

            economics = TokenEconomicsFactory.get_economics(registry=self.registry)
            stakes = StakeList(checksum_address=staker_address, registry=self.registry)
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
            self.log.info('Starting Network Crawler')
            if self._blockchain_db_client is None:
                self._blockchain_db_client = InfluxDBClient(host='localhost',
                                                            port=8086,
                                                            database=self.BLOCKCHAIN_DB_NAME)

            # start tasks
            node_learner_deferred = self._nodes_contract_info_learning_task.start(interval=self._refresh_rate, now=False)

            # hookup error callbacks
            node_learner_deferred.addErrback(self._handle_errors)

            self.start_learning_loop(now=False)

    def stop(self):
        """
        Stop the crawler if currently running
        """
        if self.is_running:
            self.log.info('Stopping Network Crawler')

            # stop tasks
            self._nodes_contract_info_learning_task.stop()

            # close connections
            self._blockchain_db_client.close()
            self._blockchain_db_client = None

    @property
    def is_running(self):
        """
        Returns True if currently running, False otherwise
        :return: True if currently running, False otherwise
        """
        return self._nodes_contract_info_learning_task.running

    @staticmethod
    def get_blockchain_crawler_client():
        return BlockchainCrawlerClient(host='localhost', port=8086, database=NetworkCrawler.BLOCKCHAIN_DB_NAME)
