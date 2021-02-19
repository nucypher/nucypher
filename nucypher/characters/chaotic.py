"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import json

import eth_utils
import math
import maya
import os
import time
from constant_sorrow.constants import NOT_RUNNING, NO_DATABASE_AVAILABLE
from datetime import datetime, timedelta
from decimal import Decimal

from eth_typing.evm import ChecksumAddress
from flask import Flask, Response
from hendrix.deploy.base import HendrixDeploy
from nacl.hash import sha256
from sqlalchemy import create_engine, or_
from twisted.internet import reactor, threads
from twisted.internet.task import LoopingCall

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.actors import NucypherTokenActor
from nucypher.blockchain.eth.agents import (ContractAgency, NucypherTokenAgent)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import FELIX_BANNER, NU_BANNER
from nucypher.characters.base import Character
from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH, TEMPLATES_DIR
from nucypher.crypto.powers import SigningPower, TransactingPower
from nucypher.datastore.deprecated import ThreadedSession
from nucypher.utilities.logging import Logger
from nucypher.network.resources import get_static_resources


class Felix(Character, NucypherTokenActor):
    """
    A NuCypher ERC20 faucet / Airdrop scheduler.

    Felix is a web application that gives NuCypher *testnet* tokens to registered addresses
    with a scheduled reduction of disbursement amounts, and an HTTP endpoint
    for handling new address registration.

    The main goal of Felix is to provide a source of testnet tokens for
    research and the development of production-ready nucypher dApps.
    """

    _default_crypto_powerups = [SigningPower]

    # Intervals
    DISTRIBUTION_INTERVAL = 60        # seconds
    DISBURSEMENT_INTERVAL = 24 * 365  # only distribute tokens to the same address once each YEAR.
    STAGING_DELAY = 10                # seconds

    # Disbursement
    BATCH_SIZE = 10                      # transactions
    MULTIPLIER = Decimal('0.9')          # 10% reduction of previous disbursement is 0.9
                                         # this is not relevant until the year of time declared above, passes.
    MINIMUM_DISBURSEMENT = int(1e18)     # NuNits (1 NU)
    ETHER_AIRDROP_AMOUNT = int(1e17)     # Wei (.1 ether)
    MAX_INDIVIDUAL_REGISTRATIONS = 3     # Registration Limit

    # Node Discovery
    LEARNING_TIMEOUT = 30           # seconds
    _SHORT_LEARNING_DELAY = 60      # seconds
    _LONG_LEARNING_DELAY = 120      # seconds
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 1

    # Twisted
    _CLOCK = reactor
    _AIRDROP_QUEUE = dict()

    class NoDatabase(RuntimeError):
        pass

    def __init__(self,
                 db_filepath: str,
                 rest_host: str,
                 rest_port: int,
                 client_password: str = None,
                 crash_on_error: bool = False,
                 distribute_ether: bool = True,
                 registry: BaseContractRegistry = None,
                 *args, **kwargs):

        # Character
        super().__init__(registry=registry, *args, **kwargs)
        self.log = Logger(f"felix-{self.checksum_address[-6::]}")

        # Network
        self.rest_port = rest_port
        self.rest_host = rest_host
        self.rest_app = NOT_RUNNING
        self.crash_on_error = crash_on_error

        # Database
        self.db_filepath = db_filepath
        self.db = NO_DATABASE_AVAILABLE
        self.db_engine = create_engine(f'sqlite:///{self.db_filepath}', convert_unicode=True)

        # Blockchain
        self.transacting_power = TransactingPower(password=client_password,
                                                  account=self.checksum_address,
                                                  signer=self.signer,
                                                  cache=True)
        self._crypto_power.consume_power_up(self.transacting_power)

        self.token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
        self.blockchain = self.token_agent.blockchain
        self.reserved_addresses = [self.checksum_address, NULL_ADDRESS]

        # Update reserved addresses with deployed contracts
        existing_entries = list(registry.enrolled_addresses)
        self.reserved_addresses.extend(existing_entries)

        # Distribution
        self.__distributed = 0    # Track NU Output
        self.__airdrop = 0        # Track Batch
        self.__disbursement = 0   # Track Quantity
        self._distribution_task = LoopingCall(f=self.airdrop_tokens)
        self._distribution_task.clock = self._CLOCK
        self.start_time = NOT_RUNNING

        self.economics = EconomicsFactory.get_economics(registry=registry)
        self.MAXIMUM_DISBURSEMENT = self.economics.maximum_allowed_locked
        self.INITIAL_DISBURSEMENT = self.economics.minimum_allowed_locked * 3

        # Optionally send ether with each token transaction
        self.distribute_ether = distribute_ether
        # Banner
        self.log.info(FELIX_BANNER.format(self.checksum_address))

    def __repr__(self):
        class_name = self.__class__.__name__
        r = f'{class_name}(checksum_address={self.checksum_address}, db_filepath={self.db_filepath})'
        return r

    def start_learning_loop(self, now=False):
        """
        Felix needs to not even be a Learner, but since it is at the moment, it certainly needs not to learn.
        """

    def make_web_app(self):
        from flask import request
        from flask_sqlalchemy import SQLAlchemy

        # WSGI/Flask Service
        short_name = bytes(self.stamp).hex()[:6]
        self.rest_app = Flask(f"faucet-{short_name}", template_folder=TEMPLATES_DIR)
        self.rest_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_filepath}'
        self.rest_app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_CONTENT_LENGTH

        try:
            self.rest_app.secret_key = sha256(os.environ['NUCYPHER_FELIX_DB_SECRET'].encode())  # uses envvar
        except KeyError:
            raise OSError("The 'NUCYPHER_FELIX_DB_SECRET' is not set.  Export your application secret and try again.")

        # Database
        self.db = SQLAlchemy(self.rest_app)

        # Database Tables
        class Recipient(self.db.Model):
            """
            The one and only table in Felix's database; Used to track recipients and airdrop metadata.
            """

            __tablename__ = 'recipient'

            id = self.db.Column(self.db.Integer, primary_key=True)
            address = self.db.Column(self.db.String, nullable=False)
            joined = self.db.Column(self.db.DateTime, nullable=False, default=datetime.utcnow)
            total_received = self.db.Column(self.db.String, default='0', nullable=False)
            last_disbursement_amount = self.db.Column(self.db.String, nullable=False, default=0)
            last_disbursement_time = self.db.Column(self.db.DateTime, nullable=True, default=None)
            is_staking = self.db.Column(self.db.Boolean, nullable=False, default=False)

            def __repr__(self):
                return f'{self.__class__.__name__}(id={self.id})'

        self.Recipient = Recipient  # Bind to outer class

        # Flask decorators
        rest_app = self.rest_app

        #
        # REST Routes
        #
        @rest_app.route("/status", methods=['GET'])
        def status():
            with ThreadedSession(self.db_engine) as session:
                total_recipients = session.query(self.Recipient).count()
                last_recipient = session.query(self.Recipient).filter(
                    self.Recipient.last_disbursement_time.isnot(None)
                ).order_by('last_disbursement_time').first()

                last_address = last_recipient.address if last_recipient else None
                last_transaction_date = last_recipient.last_disbursement_time.isoformat() if last_recipient else None

                unfunded = session.query(self.Recipient).filter(
                    self.Recipient.last_disbursement_time.is_(None)).count()

                return json.dumps(
                        {
                            "total_recipients": total_recipients,
                            "latest_recipient": last_address,
                            "latest_disburse_date": last_transaction_date,
                            "unfunded_recipients": unfunded,
                            "state": {
                                "eth": str(self.eth_balance),
                                "NU": str(self.token_balance),
                                "address": self.checksum_address,
                                "contract_address": self.token_agent.contract_address,
                            }
                        }
                    )

        @rest_app.route("/register", methods=['POST'])
        def register():
            """Handle new recipient registration via POST request."""

            new_address = (
                request.form.get('address') or
                request.get_json().get('address')
            )

            if not new_address:
                return Response(response="no address was supplied", status=411)

            if not eth_utils.is_address(new_address):
                return Response(response="an invalid ethereum address was supplied.  please ensure the address is a proper checksum.", status=400)
            else:
                new_address = eth_utils.to_checksum_address(new_address)

            if new_address in self.reserved_addresses:
                return Response(response="sorry, that address is reserved and cannot receive funds.", status=403)

            try:
                with ThreadedSession(self.db_engine) as session:

                    existing = Recipient.query.filter_by(address=new_address).all()
                    if len(existing) > self.MAX_INDIVIDUAL_REGISTRATIONS:
                        # Address already exists; Abort
                        self.log.debug(f"{new_address} is already enrolled {self.MAX_INDIVIDUAL_REGISTRATIONS} times.")
                        return Response(response=f"{new_address} requested too many times  -  Please use another address.", status=409)

                    # Create the record
                    recipient = Recipient(address=new_address, joined=datetime.now())
                    session.add(recipient)
                    session.commit()

            except Exception as e:
                # Pass along exceptions to the logger
                self.log.critical(str(e))
                raise

            else:
                return Response(status=200)  # TODO

        return rest_app

    def create_tables(self) -> None:
        self.make_web_app()
        return self.db.create_all(app=self.rest_app)

    def start(self,
              host: str,
              port: int,
              web_services: bool = True,
              distribution: bool = True,
              crash_on_error: bool = False):

        self.crash_on_error = crash_on_error

        if self.start_time is not NOT_RUNNING:
            raise RuntimeError("Felix is already running.")

        self.start_time = maya.now()
        payload = {"wsgi": self.rest_app, "http_port": port, "resources": get_static_resources()}
        deployer = HendrixDeploy(action="start", options=payload)

        if distribution is True:
            self.start_distribution()

        if web_services is True:
            deployer.run()  # <-- Blocking call (Reactor)

    def start_distribution(self, now: bool = True) -> bool:
        """Start token distribution"""
        self.log.info(NU_BANNER)
        self.log.info("Starting NU Token Distribution | START")
        if self.token_balance == NU.ZERO():
            raise self.ActorError(f"Felix address {self.checksum_address} has 0 NU tokens.")
        self._distribution_task.start(interval=self.DISTRIBUTION_INTERVAL, now=now)
        return True

    def stop_distribution(self) -> bool:
        """Start token distribution"""
        self.log.info("Stopping NU Token Distribution | STOP")
        self._distribution_task.stop()
        return True

    def __calculate_disbursement(self, recipient: ChecksumAddress) -> int:
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
        receipt = self.token_agent.transfer(amount=disbursement,
                                            target_address=recipient_address,
                                            transacting_power=self.transacting_power)
        txhash = receipt['transactionHash']
        if self.distribute_ether:
            ether = self.ETHER_AIRDROP_AMOUNT
            transaction = {'to': recipient_address,
                           'from': self.checksum_address,
                           'value': ether,
                           'gasPrice': self.blockchain.client.gas_price_for_transaction()}

            transaction_dict = self.blockchain.build_payload(sender_address=self.checksum_address,
                                                             payload=transaction,
                                                             transaction_gas_limit=22000)
            _receipt = self.blockchain.sign_and_broadcast_transaction(transacting_power=self.transacting_power,
                                                                      transaction_dict=transaction_dict,
                                                                      transaction_name='transfer')
            self.log.info(f"Disbursement #{self.__disbursement} OK | NU {txhash.hex()[-6:]}"
                          f"({str(NU(disbursement, 'NuNit'))} + {self.ETHER_AIRDROP_AMOUNT} wei) -> {recipient_address}")
        else:
            self.log.info(
                f"Disbursement #{self.__disbursement} OK"
                f"({str(NU(disbursement, 'NuNit'))} -> {recipient_address}")

        return txhash

    def airdrop_tokens(self):
        """
        Calculate airdrop eligibility via faucet registration
        and transfer tokens to selected recipients.
        """

        with ThreadedSession(self.db_engine) as session:
            population = session.query(self.Recipient).count()

        message = f"{population} registered faucet recipients; " \
                  f"Distributed {str(NU(self.__distributed, 'NuNit'))} since {self.start_time.slang_time()}."
        self.log.debug(message)
        if population == 0:
            return  # Abort - no recipients are registered.

        # For filtration
        since = datetime.now() - timedelta(hours=self.DISBURSEMENT_INTERVAL)

        datetime_filter = or_(self.Recipient.last_disbursement_time <= since,
                              self.Recipient.last_disbursement_time == None)  # This must be `==` not `is`

        with ThreadedSession(self.db_engine) as session:
            candidates = session.query(self.Recipient).filter(datetime_filter).all()
            if not candidates:
                self.log.info("No eligible recipients this round.")
                return

        # Discard invalid addresses, in-depth
        invalid_addresses = list()

        def siphon_invalid_entries(candidate):
            address_is_valid = eth_utils.is_checksum_address(candidate.address)
            if not address_is_valid:
                invalid_addresses.append(candidate.address)
            return address_is_valid

        candidates = list(filter(siphon_invalid_entries, candidates))

        if invalid_addresses:
            self.log.info(f"{len(invalid_addresses)} invalid entries detected. Pruning database.")

            # TODO: Is this needed? - Invalid entries are rejected at the endpoint view.
            # Prune database of invalid records
            # with ThreadedSession(self.db_engine) as session:
            #     bad_eggs = session.query(self.Recipient).filter(self.Recipient.address in invalid_addresses).all()
            #     for egg in bad_eggs:
            #         session.delete(egg.id)
            #     session.commit()

        if not candidates:
            self.log.info("No eligible recipients this round.")
            return

        d = threads.deferToThread(self.__do_airdrop, candidates=candidates)
        self._AIRDROP_QUEUE[self.__airdrop] = d
        return d

    def __do_airdrop(self, candidates: list):

        self.log.info(f"Staging Airdrop #{self.__airdrop}.")

        # Staging
        staged_disbursements = [(r, self.__calculate_disbursement(recipient=r)) for r in candidates]
        batches = list(staged_disbursements[index:index+self.BATCH_SIZE] for index in range(0, len(staged_disbursements), self.BATCH_SIZE))
        total_batches = len(batches)

        self.log.info("====== Staged Airdrop ======")
        for recipient, disbursement in staged_disbursements:
            self.log.info(f"{recipient.address} ... {str(disbursement)[:-18]}")
        self.log.info("==========================")

        # Staging Delay
        self.log.info(f"Airdrop will commence in {self.STAGING_DELAY} seconds...")
        if self.STAGING_DELAY > 3:
            time.sleep(self.STAGING_DELAY - 3)
        for i in range(3):
            time.sleep(1)
            self.log.info(f"NU Token airdrop starting in {3 - i} seconds...")

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

        del self._AIRDROP_QUEUE[self.__airdrop]
        self.__airdrop += 1
