import os
from collections import namedtuple

import pytest
from eth_utils.address import to_checksum_address
from twisted.logger import globalLogPublisher, LogLevel

from bytestring_splitter import VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED

from nucypher.characters.base import Character
from nucypher.crypto.powers import TransactingPower
from nucypher.network.nicknames import nickname_from_seed
from nucypher.network.nodes import FleetStateTracker
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas, make_ursula_for_staker


def test_blockchain_ursula_stamp_verification_tolerance(blockchain_ursulas):
    #
    # Setup
    #

    lonely_blockchain_learner, blockchain_teacher, unsigned, *the_others = list(blockchain_ursulas)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    #
    # Attempt to verify unsigned stamp
    #
    unsigned._Teacher__decentralized_identity_evidence = NOT_SIGNED

    # Wipe known nodes!
    lonely_blockchain_learner._Learner__known_nodes = FleetStateTracker()
    lonely_blockchain_learner._current_teacher_node = blockchain_teacher
    lonely_blockchain_learner.remember_node(blockchain_teacher)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node()
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned) in warning
    assert "stamp is unsigned" in warning  # TODO: Cleanup logging templates
    assert unsigned not in lonely_blockchain_learner.known_nodes

    # minus 2: self and the unsigned ursula.
    assert len(lonely_blockchain_learner.known_nodes) == len(blockchain_ursulas) - 2
    assert blockchain_teacher in lonely_blockchain_learner.known_nodes


@pytest.mark.skip("See Issue #1075")  # TODO: Issue #1075
def test_invalid_workers_tolerance(testerchain,
                                   blockchain_ursulas,
                                   agency,
                                   idle_staker,
                                   token_economics,
                                   ursula_decentralized_test_config
                                   ):
    #
    # Setup
    #
    lonely_blockchain_learner, blockchain_teacher, unsigned, *the_others = list(blockchain_ursulas)
    _, staking_agent, _ = agency

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # We start with an "idle_staker" (i.e., no tokens in StakingEscrow)
    assert 0 == staking_agent.owned_tokens(idle_staker.checksum_address)

    # Now let's create an active worker for this staker.
    # First, stake something (e.g. the bare minimum)
    amount = token_economics.minimum_allowed_locked
    periods = token_economics.minimum_locked_periods

    # Mock Powerup consumption (Staker)
    testerchain.transacting_power = TransactingPower(account=idle_staker.checksum_address)

    idle_staker.initialize_stake(amount=amount, lock_periods=periods)

    # Stake starts next period (or else signature validation will fail)
    testerchain.time_travel(periods=1)
    idle_staker.stake_tracker.refresh()

    # We create an active worker node for this staker
    worker = make_ursula_for_staker(staker=idle_staker,
                                    worker_address=testerchain.unassigned_accounts[-1],
                                    ursula_config=ursula_decentralized_test_config,
                                    blockchain=testerchain,
                                    confirm_activity=True,
                                    ursulas_to_learn_about=None)

    # Since we confirmed activity, we need to advance one period
    testerchain.time_travel(periods=1)

    # The worker is valid and can be verified (even with the force option)
    worker.verify_node(force=True, network_middleware=MockRestMiddleware(), certificate_filepath="quietorl")
    # In particular, we know that it's bonded to a staker who is really staking.
    assert worker._worker_is_bonded_to_staker()
    assert worker._staker_is_really_staking()

    # OK. Now we learn about this worker.
    lonely_blockchain_learner.remember_node(worker)

    # The worker already confirmed one period before. Let's confirm the remaining 29.
    for i in range(29):
        worker.confirm_activity()
        testerchain.time_travel(periods=1)

    # The stake period has ended, and the staker wants her tokens back ("when lambo?").
    # She withdraws up to the last penny (well, last nunit, actually).

    # Mock Powerup consumption (Staker)
    testerchain.transacting_power = TransactingPower(account=idle_staker.checksum_address)
    idle_staker.mint()
    testerchain.time_travel(periods=1)
    i_want_it_all = staking_agent.owned_tokens(idle_staker.checksum_address)
    idle_staker.withdraw(i_want_it_all)

    # OK...so...the staker is not staking anymore ...
    assert 0 == staking_agent.owned_tokens(idle_staker.checksum_address)

    # ... but the worker node still is "verified" (since we're not forcing on-chain verification)
    worker.verify_node(network_middleware=MockRestMiddleware(), certificate_filepath="quietorl")

    # If we force, on-chain verification, the worker is of course not verified
    with pytest.raises(worker.NotStaking):
        worker.verify_node(force=True, network_middleware=MockRestMiddleware(), certificate_filepath="quietorl")


    # Let's learn from this invalid node
    lonely_blockchain_learner._current_teacher_node = worker
    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node()
    # lonely_blockchain_learner.remember_node(worker)  # The same problem occurs if we directly try to remember this node
    globalLogPublisher.removeObserver(warning_trapper)

    # TODO: What should we really check here? (#1075)
    assert len(warnings) == 1
    warning = warnings[-1]['log_format']
    assert str(worker) in warning
    assert "no active stakes" in warning  # TODO: Cleanup logging templates
    assert worker not in lonely_blockchain_learner.known_nodes

    # TODO: Write a similar test but for detached worker (#1075)


def test_emit_warning_upon_new_version(ursula_federated_test_config, caplog):
    nodes = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                   quantity=3,
                                   know_each_other=False)
    teacher, learner, new_node = nodes

    learner.remember_node(teacher)
    teacher.remember_node(learner)
    teacher.remember_node(new_node)

    new_node.TEACHER_VERSION = learner.LEARNER_VERSION + 1

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)
    learner.learn_from_teacher_node()

    assert len(warnings) == 1
    assert warnings[0]['log_format'] == learner.unknown_version_message.format(new_node,
                                                                               new_node.TEACHER_VERSION,
                                                                               learner.LEARNER_VERSION)

    # Now let's go a little further: make the version totally unrecognizable.

    # First, there's enough garbage to at least scrape a potential checksum staker_address
    fleet_snapshot = os.urandom(32 + 4)
    random_bytes = os.urandom(50)  # lots of garbage in here
    future_version = learner.LEARNER_VERSION + 42
    version_bytes = future_version.to_bytes(2, byteorder="big")
    crazy_bytes = fleet_snapshot + VariableLengthBytestring(version_bytes + random_bytes)
    signed_crazy_bytes = bytes(teacher.stamp(crazy_bytes))

    Response = namedtuple("MockResponse", ("content", "status_code"))
    response = Response(content=signed_crazy_bytes + crazy_bytes, status_code=200)

    learner._current_teacher_node = teacher
    learner.network_middleware.get_nodes_via_rest = lambda *args, **kwargs: response
    learner.learn_from_teacher_node()

    # If you really try, you can read a node representation from the garbage
    accidental_checksum = to_checksum_address(random_bytes[:20])
    accidental_nickname = nickname_from_seed(accidental_checksum)[0]
    accidental_node_repr = Character._display_name_template.format("Ursula", accidental_nickname, accidental_checksum)

    assert len(warnings) == 2
    assert warnings[1]['log_format'] == learner.unknown_version_message.format(accidental_node_repr,
                                                                               future_version,
                                                                               learner.LEARNER_VERSION)

    # This time, however, there's not enough garbage to assume there's a checksum staker_address...
    random_bytes = os.urandom(2)
    crazy_bytes = fleet_snapshot + VariableLengthBytestring(version_bytes + random_bytes)
    signed_crazy_bytes = bytes(teacher.stamp(crazy_bytes))

    response = Response(content=signed_crazy_bytes + crazy_bytes, status_code=200)

    learner._current_teacher_node = teacher
    learner.learn_from_teacher_node()

    assert len(warnings) == 3
    # ...so this time we get a "really unknown version message"
    assert warnings[2]['log_format'] == learner.really_unknown_version_message.format(future_version,
                                                                                      learner.LEARNER_VERSION)

    globalLogPublisher.removeObserver(warning_trapper)


def test_node_posts_future_version(federated_ursulas):
    ursula = list(federated_ursulas)[0]
    middleware = MockRestMiddleware()

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)

    crazy_node = b"invalid-node"
    middleware.get_nodes_via_rest(node=ursula,
                                  announce_nodes=(crazy_node,))
    assert len(warnings) == 1
    future_node = list(federated_ursulas)[1]
    future_node.TEACHER_VERSION = future_node.TEACHER_VERSION + 10
    future_node_bytes = bytes(future_node)
    middleware.get_nodes_via_rest(node=ursula,
                                  announce_nodes=(future_node_bytes,))
    assert len(warnings) == 2
