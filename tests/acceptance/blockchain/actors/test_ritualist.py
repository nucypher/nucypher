import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from tests.utils.ursula import start_pytest_ursula_services


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, agency, testerchain, control_time, test_registry, alice):

    cohort = list(sorted(ursulas[:CoordinatorAgent.DKG_SIZE], key=lambda x: int(x.operator_address, 16)))
    coordinator_agent = ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)

    for u in cohort:
        start_pytest_ursula_services(u)
        u.ritual_tracker.task.clock = control_time
        d = u.ritual_tracker.start()

    def initiate_ritual(r):
        nodes = [u.operator_address for u in cohort]
        receipt = coordinator_agent.initiate_ritual(nodes=nodes, transacting_power=alice.transacting_power)

    def scan(*args, **kwargs):
        for u in cohort:
            u.ritual_tracker.scan()

    def time_travel(r):
        delta = 20  # seconds
        testerchain.time_travel(seconds=delta)
        # for _ in range(delta):
        control_time.advance(delta)

    def assert_ritual_tracker(r):
        assert coordinator_agent.number_of_rituals() == 1
        assert len(cohort[0].ritual_tracker.rituals) == 1

    def assert_checkins(r):
        ritual = cohort[0].get_ritual(0)
        assert ritual.total_checkins == coordinator_agent.DKG_SIZE

    def assert_transcripts(r):
        ritual = cohort[0].get_ritual(0)
        assert ritual.total_transcripts == coordinator_agent.DKG_SIZE

    def assert_confirmations(r):
        ritual = cohort[0].get_ritual(0)
        assert ritual.total_confirmations == coordinator_agent.DKG_SIZE


    # Round 0
    # Initiate the ritual
    d.addCallback(initiate_ritual)
    # assert that the ritual tracker has been updated
    d.addCallback(time_travel)

    d = deferToThread(scan)
    d.addCallback(assert_ritual_tracker)

    # Round 0
    # assert that the checkins have been updated
    d.addCallback(time_travel)
    d = deferToThread(scan)
    d.addCallback(assert_checkins)

    # Round 1
    # assert that the transcripts have been updated
    d.addCallback(time_travel)
    d = deferToThread(scan)
    d.addCallback(assert_transcripts)

    # Round 2
    # assert that the confirmations have been updated
    d.addCallback(time_travel)
    d = deferToThread(scan)
    d.addCallback(assert_confirmations)

    yield d
