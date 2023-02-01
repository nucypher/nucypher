import time

import pytest_twisted
from twisted.internet.defer import DeferredList
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from tests.utils.ursula import start_pytest_ursula_services


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, agency, testerchain, test_registry, alice, control_time):

    EventScannerTask.INTERVAL = .1

    cohort = list(sorted(ursulas[:CoordinatorAgent.DKG_SIZE], key=lambda x: int(x.operator_address, 16)))
    assert len(cohort) == CoordinatorAgent.DKG_SIZE
    coordinator_agent = ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)
    node = cohort[0]

    # Start Ursula services
    def start_ursulas():
        for ursula in cohort:
            ursula.ritual_tracker.start()
            start_pytest_ursula_services(ursula=ursula)

    # Round 0 - Initiate the ritual
    def initialize(r):
        print("==================== INITIALIZING ====================")
        nodes = [u.operator_address for u in cohort]
        coordinator_agent.initiate_ritual(nodes=nodes, transacting_power=alice.transacting_power)

    # Round 0 - Initiate the ritual
    def check_initialize(r):
        print("==================== CHECKING INITIALIZATION ====================")
        assert coordinator_agent.number_of_rituals() == 1
        node.ritual_tracker.refresh()
        # assert len(node.ritual_tracker.rituals) == 1

    # Checkins
    def round0(r):
        print("==================== ROUND 0 ====================")
        assert node.ritual_tracker.get_ritual(0).total_checkins == coordinator_agent.DKG_SIZE, \
            "Not all checkins were received for round 0"
        # assert node.ritual_tracker.get_ritual(0).status == coordinator_agent.RitualStatus.WAITING_FOR_TRANSCRIPTS

    # Transcripts
    def round1(r):
        print("==================== ROUND 1 ====================")
        assert node.ritual_tracker.get_ritual(0).total_transcripts == coordinator_agent.DKG_SIZE, \
            "Not all transcripts were received for round 1"
        # assert node.ritual_tracker.get_ritual(0).status == coordinator_agent.RitualStatus.WAITING_FOR_CONFIRMATIONS

    # Confirmations
    def round2(r):
        print("==================== ROUND 2 ====================")
        assert node.ritual_tracker.get_ritual(0).total_confirmations == coordinator_agent.DKG_SIZE, \
            "Not all confirmations were received for round 2"
        # assert node.ritual_tracker.get_ritual(0).status == coordinator_agent.RitualStatus.COMPLETED

    def block_until_round(d, round: int):
        r = {
            0: 'total_checkins',
            1: 'total_transcripts',
            2: 'total_confirmations',
        }

        while getattr(node.ritual_tracker.get_ritual(0), r[round]) < coordinator_agent.DKG_SIZE:
            # testerchain.time_travel(seconds=1)
            control_time.advance(1)
            # for ursula in cohort:
            #     ursula.ritual_tracker.scan()


    d = deferToThread(start_ursulas)
    d.addCallback(initialize)

    # yield d

    d.addCallback(lambda _: block_until_round(d, 0))
    d.addCallback(check_initialize)
    d.addCallback(round0)

    yield d

    d.addCallback(lambda _: block_until_round(d, 1))
    d.addCallback(round1)

    yield d

    d.addCallback(lambda _: block_until_round(d, 2))
    d.addCallback(round2)

    yield d
