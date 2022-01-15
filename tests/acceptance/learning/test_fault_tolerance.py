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

import pytest
from twisted.logger import LogLevel, globalLogPublisher
from constant_sorrow.constants import NOT_SIGNED

from nucypher.core import MetadataResponse

from nucypher.acumen.perception import FleetSensor
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.signing import InvalidSignature
from nucypher.network.nodes import Learner
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import make_ursula_for_staker


def test_blockchain_ursula_stamp_verification_tolerance(blockchain_ursulas, mocker):
    #
    # Setup
    #

    lonely_blockchain_learner, blockchain_teacher, unsigned, *the_others = list(blockchain_ursulas)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # Make a bad identity evidence
    unsigned._Teacher__decentralized_identity_evidence = unsigned._Teacher__decentralized_identity_evidence[:-5] + (b'\x00' * 5)
    # Reset the metadata cache
    unsigned._metadata = None

    # Wipe known nodes!
    lonely_blockchain_learner._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    lonely_blockchain_learner._current_teacher_node = blockchain_teacher
    lonely_blockchain_learner.remember_node(blockchain_teacher)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned) in warning
    assert "Verification Failed" in warning  # TODO: Cleanup logging templates

    # TODO: Buckets!  #567
    # assert unsigned not in lonely_blockchain_learner.known_nodes

    # minus 2: self and the unsigned ursula.
    # assert len(lonely_blockchain_learner.known_nodes) == len(blockchain_ursulas) - 2
    assert blockchain_teacher in lonely_blockchain_learner.known_nodes

    # Learn about a node with a badly signed payload

    def bad_bytestring_of_known_nodes():
        # Signing with the learner's signer instead of the teacher's signer
        response = MetadataResponse.author(signer=lonely_blockchain_learner.stamp.as_umbral_signer(),
                                           timestamp_epoch=blockchain_teacher.known_nodes.timestamp.epoch)
        return bytes(response)

    mocker.patch.object(blockchain_teacher, 'bytestring_of_known_nodes', bad_bytestring_of_known_nodes)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 2
    warning = warnings[1]['log_format']
    assert str(blockchain_teacher) in warning
    assert "Invalid signature received from teacher" in warning  # TODO: Cleanup logging templates


@pytest.mark.skip("See Issue #1075")  # TODO: Issue #1075
def test_invalid_workers_tolerance(testerchain,
                                   test_registry,
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

    idle_staker.initialize_stake(amount=amount, lock_periods=periods)

    # Stake starts next period (or else signature validation will fail)
    testerchain.time_travel(periods=1)
    idle_staker.stake_tracker.refresh()

    # We create an active worker node for this staker
    worker = make_ursula_for_staker(staker=idle_staker,
                                    worker_address=testerchain.unassigned_accounts[-1],
                                    ursula_config=ursula_decentralized_test_config,
                                    blockchain=testerchain,
                                    ursulas_to_learn_about=None)

    # Since we made a commitment, we need to advance one period
    testerchain.time_travel(periods=1)

    # The worker is valid and can be verified (even with the force option)
    worker.verify_node(force=True, network_middleware=MockRestMiddleware(), certificate_filepath="quietorl")
    # In particular, we know that it's bonded to a staker who is really staking.
    assert worker._worker_is_bonded_to_staker(registry=test_registry)
    assert worker._staker_is_really_staking(registry=test_registry)

    # OK. Now we learn about this worker.
    lonely_blockchain_learner.remember_node(worker)

    # The worker already committed one period before. Let's commit to the remaining 29.
    for i in range(29):
        worker.commit_to_next_period()
        testerchain.time_travel(periods=1)

    # The stake period has ended, and the staker wants her tokens back ("when lambo?").
    # She withdraws up to the last penny (well, last nunit, actually).

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
