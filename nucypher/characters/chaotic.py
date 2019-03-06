import json
import time
from datetime import datetime, timedelta

import math
import os

import click
import maya
from flask import Flask, render_template, Response
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, scoped_session
from twisted.internet import threads
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

from hendrix.deploy.base import HendrixDeploy
from hendrix.experience import hey_joe
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MAX_ALLOWED_LOCKED, HOURS_PER_PERIOD
from nucypher.characters.banners import MOE_BANNER, FELIX_BANNER, NU_BANNER
from nucypher.characters.base import Character
from nucypher.config.constants import TEMPLATES_DIR
from nucypher.crypto.powers import SigningPower
from nucypher.network.nodes import FleetStateTracker


class Moe(Character):
    """
    A monitor (lizard?)
    """
    banner = MOE_BANNER

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log.info(self.banner)

    class MonitoringTracker(FleetStateTracker):
        def record_fleet_state(self, *args, **kwargs):
            new_state_or_none = super().record_fleet_state(*args, **kwargs)
            if new_state_or_none:
                checksum, new_state = new_state_or_none
                hey_joe.send({checksum: self.abridged_state_details(new_state)}, "states")
            return new_state_or_none

    tracker_class = MonitoringTracker
    _SHORT_LEARNING_DELAY = .5
    _LONG_LEARNING_DELAY = 30
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    def remember_node(self, *args, **kwargs):
        new_node_or_none = super().remember_node(*args, **kwargs)
        if new_node_or_none:
            hey_joe.send(
                {new_node_or_none.checksum_public_address: Moe.MonitoringTracker.abridged_node_details(new_node_or_none)},
                "nodes")
        return new_node_or_none

    def learn_from_teacher_node(self, *args, **kwargs):
        teacher = self.current_teacher_node(cycle=False)
        new_nodes = super().learn_from_teacher_node(*args, **kwargs)
        hey_joe.send({teacher.checksum_public_address: Moe.MonitoringTracker.abridged_node_details(teacher)}, "nodes")
        new_teacher = self.current_teacher_node(cycle=False)
        hey_joe.send({"current_teacher": new_teacher.checksum_public_address}, "teachers")
        return new_nodes

    def start(self, ws_port: int, http_port: int, dry_run: bool = False):

        #
        # Websocket Service
        #

        def send_states(subscriber):
            message = ["states", self.known_nodes.abridged_states_dict()]
            subscriber.sendMessage(json.dumps(message).encode())

        def send_nodes(subscriber):
            message = ["nodes", self.known_nodes.abridged_nodes_dict()]
            subscriber.sendMessage(json.dumps(message).encode())

        websocket_service = hey_joe.WebSocketService("127.0.0.1", ws_port)
        websocket_service.register_followup("states", send_states)
        websocket_service.register_followup("nodes", send_nodes)

        #
        # WSGI Service
        #

        self.rest_app = Flask("fleet-monitor", template_folder=TEMPLATES_DIR)
        rest_app = self.rest_app

        @rest_app.route("/")
        def status():
            try:
                return render_template('monitor.html')
            except Exception as e:
                self.log.debug(str(e))

        #
        # Server
        #

        deployer = HendrixDeploy(action="start", options={"wsgi": rest_app, "http_port": http_port})
        deployer.add_non_tls_websocket_service(websocket_service)

        click.secho(f"Running Moe on 127.0.0.1:{http_port}")

        if not dry_run:
            deployer.run()


class Felix(Character):
    """
    A NuCypher testnet ERC20 faucet.

    Felix is a web application that gives NuCypher *testnet* tokens to registered addresses
    with a scheduled reduction of disbursement amounts, and a web-page for handling new registration.

    The main goal of Felix is to provide a source of testnet tokens for
    the development of production-ready nucypher dApps.
    """

    _default_crypto_powerups = [SigningPower]  # identity only

    DISTRIBUTION_INTERVAL = 60*60              # seconds
    DISBURSEMENT_INTERVAL = HOURS_PER_PERIOD   # (24) hours
    BATCH_SIZE = 10                            # transactions
    MULTIPLIER = 0.95                          # 5% reduction of each stake is 0.95, for example
    MAXIMUM_DISBURSEMENT = MAX_ALLOWED_LOCKED  # NU-wei
    INITIAL_DISBURSEMENT = MIN_ALLOWED_LOCKED  # NU-wei
    MINIMUM_DISBURSEMENT = 1e18                # NU-wei

    # Node Discovery
    LEARNING_TIMEOUT = 30                      # seconds
    _SHORT_LEARNING_DELAY = 60                 # seconds
    _LONG_LEARNING_DELAY = 120                 # seconds
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 1

    class NoDatabase(RuntimeError):
        pass

    def __init__(self,
                 db_filepath: str,
                 rest_host: str,
                 rest_port: int,
                 *args, **kwargs):

        # Character
        super().__init__(*args, **kwargs)
        self.log = Logger(f"felix-{self.checksum_public_address[-6::]}")

        # Network
        self.rest_port = rest_port
        self.rest_host = rest_host
        self.rest_app = None

        # Database
        self.db_filepath = db_filepath
        self.db = None
        self.engine = create_engine(f'sqlite://{self.db_filepath}', convert_unicode=True)

        # Blockchain
        self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)

        # Distribution
        self.__distributed = 0    # Track NU Output
        self.__airdrop = 0        # Track Batch
        self.__disbursement = 0   # Track Quantity
        self._distribution_task = LoopingCall(self.airdrop_tokens)
        self.start_time = None

        # Banner
        self.log.info(FELIX_BANNER.format(self.checksum_public_address))

    def __repr__(self):
        class_name = self.__class__.__name__
        r = f'{class_name}(checksum_address={self.checksum_public_address}, db_filepath={self.db_filepath})'
        return r

    def make_web_app(self):
        from flask import request
        from flask_sqlalchemy import SQLAlchemy

        # WSGI/Flask Service
        short_name = bytes(self.stamp).hex()[:6]
        self.rest_app = Flask(f"faucet-{short_name}", template_folder=TEMPLATES_DIR)

        # Flask Settings
        self.rest_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_filepath}'
        self.rest_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        self.rest_app.secret_key = "flask rocks!"  # FIXME: NO!!!

        # Database
        self.db = SQLAlchemy(self.rest_app)

        class Recipient(self.db.Model):
            __tablename__ = 'recipient'

            id = self.db.Column(self.db.Integer, primary_key=True)
            address = self.db.Column(self.db.String, unique=True, nullable=False)
            joined = self.db.Column(self.db.DateTime, nullable=False)
            total_received = self.db.Column(self.db.String, default='0', nullable=False)
            last_disbursement_amount = self.db.Column(self.db.String, nullable=True)
            last_disbursement_time = self.db.Column(self.db.DateTime, nullable=True)
            is_staking = self.db.Column(self.db.Boolean, default=False)

            def __repr__(self):
                class_name = self.__class__.__name__
                return f"{class_name}(address={self.address}, amount_received={self.total_received})"

        # Bind to outer class
        self.Recipient = Recipient

        # Decorator
        rest_app = self.rest_app

        @rest_app.route("/", methods=['GET'])
        def home():
            return render_template('felix.html')

        @rest_app.route("/register", methods=['POST'])
        def register():
            try:
                new_address = request.form['address']

                existing = Recipient.query.filter_by(address=new_address).all()
                if existing:
                    # Address already exists; Abort
                    return Response(status=400)

                # Create the record
                recipient = Recipient(address=new_address, joined=datetime.now())
                self.db.session.add(recipient)
                self.db.session.commit()

            except Exception as e:
                self.log.critical(str(e))

            return Response(status=200)

        return rest_app

    def create_tables(self) -> None:
        return self.db.create_all(app=self.rest_app)

    def start(self,
              host: str,
              port: int,
              web_services: bool = True,
              distribution: bool = True):

        self.start_time = maya.now()
        payload = {"wsgi": self.rest_app, "http_port": port}
        deployer = HendrixDeploy(action="start", options=payload)
        click.secho(f"Running {self.__class__.__name__} on {host}:{port}")

        if distribution is True:
            self.start_distribution()

        if web_services is True:
            deployer.run()  # <-- Blocking call (Reactor)

    def start_distribution(self, now: bool = True) -> bool:
        """Start token distribution"""
        self.log.info(NU_BANNER)
        self.log.info("Starting NU Token Distribution NOW")
        self._distribution_task.start(interval=self.DISTRIBUTION_INTERVAL, now=now)
        return True

    def stop_distribution(self) -> bool:
        """Start token distribution"""
        self._distribution_task.stop()
        return True

    def __calculate_disbursement(self, recipient) -> int:
        """Calculate the next reward for a recipient once the are selected for distribution"""

        # Initial Reward - sets the future rates
        if recipient.last_disbursement_time is None:
            amount = self.INITIAL_DISBURSEMENT

        # Cap reached, We'll continue to leak the minimum disbursement
        elif int(recipient.total_received) >= self.MAXIMUM_DISBURSEMENT:
            amount = self.MINIMUM_DISBURSEMENT

        # Calculate the next disbursement
        else:
            amount = math.ceil(int(recipient.last_disbursement_amount) * self.MULTIPLIER)
            if amount < self.MINIMUM_DISBURSEMENT:
                amount = self.MINIMUM_DISBURSEMENT

        return int(amount)

    def __transfer(self, disbursement: int, recipient_address: str) -> str:
        """Perform a single token transfer transaction from one account to another."""

        self.__disbursement += 1
        txhash = self.token_agent.transfer(amount=disbursement,
                                           target_address=recipient_address,
                                           sender_address=self.checksum_public_address)

        self.log.info(f"Disbursement #{self.__disbursement} OK | {txhash.hex()[-6:]} | "
                      f"({str(disbursement)[:-18]} NU) -> {recipient_address}")
        return txhash

    def airdrop_tokens(self):
        """
        Calculate airdrop eligibility via faucet registration
        and transfer tokens to selected recipients.
        """

        population = self.Recipient.query.count()
        message = f"{population} registered faucet recipients; " \
                  f"Distributed {str(self.__distributed)[:-18] or 0} NU since {self.start_time.slang_time()}."
        self.log.debug(message)
        if population is 0:
            return  # Abort - no recipients are registered.

        # For filtration
        since = datetime.now() - timedelta(hours=self.DISBURSEMENT_INTERVAL)

        datetime_filter = or_(self.Recipient.last_disbursement_time <= since,
                              self.Recipient.last_disbursement_time == None)

        candidates = self.Recipient.query.filter(datetime_filter).all()
        if not candidates:
            self.log.info("No eligible recipients this round.")
            return

        self.log.info(f"Staging Airdrop #{self.__airdrop}.")

        # Staging
        staged_disbursements = [(r, self.__calculate_disbursement(recipient=r)) for r in candidates]
        batches = list(staged_disbursements[index:index+self.BATCH_SIZE] for index in range(0, len(staged_disbursements), self.BATCH_SIZE))
        total_batches = len(batches)

        self.log.info("====== Staged Stage ======")
        for recipient, disbursement in staged_disbursements:
            self.log.info(f"{recipient.address} ... {str(disbursement)[:-18]}")
        self.log.info("==========================")

        # Slowly, in series...
        for batch, staged_disbursement in enumerate(batches, start=1):
            self.log.info(f"======= Batch #{batch} ========")

            for recipient, disbursement in staged_disbursement:

                # Perform the transfer... leaky faucet.
                self.__transfer(disbursement=disbursement, recipient_address=recipient.address)
                self.__distributed += disbursement

                # Update the database record
                recipient.last_disbursement_amount = str(disbursement)
                recipient.total_received = str(int(recipient.total_received) + disbursement)
                recipient.last_disbursement_time = datetime.now()

                self.db.session.add(recipient)
                self.db.session.commit()

            # end inner loop
            self.log.info(f"Completed Airdrop #{self.__airdrop} Batch #{batch} of {total_batches}.")

        # end outer loop
        now = maya.now()
        next_interval_slang = now.add(seconds=self.DISTRIBUTION_INTERVAL).slang_time()
        self.log.info(f"Completed Airdrop #{self.__airdrop}; Next airdrop is {next_interval_slang}.")
        self.__airdrop += 1

