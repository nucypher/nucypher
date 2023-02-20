import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from tests.utils.ursula import start_pytest_ursula_services

DKG_SIZE = 3

@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, agency, testerchain, test_registry, alice, control_time):

    EventScannerTask.INTERVAL = 10

    cohort = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.operator_address, 16)))
    assert len(cohort) == DKG_SIZE
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
        receipt = coordinator_agent.initiate_ritual(nodes=nodes, transacting_power=alice.transacting_power)
        return receipt

    # Round 0 - Initiate the ritual
    def check_initialize(receipt):
        print("==================== CHECKING INITIALIZATION ====================")
        testerchain.wait_for_receipt(receipt['transactionHash'])
        assert coordinator_agent.number_of_rituals() == 1
        node.ritual_tracker.refresh(fetch_rituals=[0])
        assert len(node.ritual_tracker.rituals) == 1
        assert coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS

    # Transcripts
    def round1(r):
        print("==================== ROUND 1 ====================")
        testerchain.time_travel(seconds=60)
        assert node.ritual_tracker.get_ritual(0).total_transcripts == DKG_SIZE, "missing transcripts"
        assert coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.AWAITING_AGGREGATIONS

    # Aggregations
    def round2(r):
        print("==================== ROUND 2 ====================")
        testerchain.time_travel(seconds=60)
        assert node.ritual_tracker.get_ritual(0).total_aggregations == DKG_SIZE, "missing aggregations"
        assert node.ritual_tracker.get_ritual(0).status == coordinator_agent.Ritual.Status.FINALIZED


    def block_until_round(d, round: int):
        r = {
            1: 'total_transcripts',
            2: 'total_aggregations',
        }

        while getattr(node.ritual_tracker.get_ritual(0), r[round]) < DKG_SIZE:
            testerchain.time_travel(seconds=60)
            control_time.advance(60)
            for ursula in cohort:
                ursula.ritual_tracker.scan()
                ursula.ritual_tracker.refresh()

    d = deferToThread(start_ursulas)

    d.addCallback(initialize)
    d.addCallback(check_initialize)
    yield d

    d.addCallback(lambda r: block_until_round(d, 1))
    d.addCallback(round1)
    yield d

    d.addCallback(lambda r: block_until_round(d, 2))
    d.addCallback(round2)
    yield d
