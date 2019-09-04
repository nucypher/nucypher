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
from mock import Mock

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.blockchain.eth.actors import Staker, Investigator
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.signing import SignatureStamp


def mock_ursula(testerchain, account):
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


@pytest.mark.slow()
def test_investigator_requests_slashing(testerchain,
                                        test_registry,
                                        session_agency,
                                        mock_ursula_reencrypts,
                                        token_economics,
                                        slashing_economics):
    testerchain = testerchain

    staker_account = testerchain.staker_account(0)
    worker_account = testerchain.ursula_account(0)

    ##### STAKING ESCROW STUFF #####

    token_agent, staking_agent, _policy_agent = session_agency

    locked_tokens = token_economics.minimum_allowed_locked * 5

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = TransactingPower(account=testerchain.etherbase_account)
    testerchain.transacting_power.activate()

    # The staker receives an initial amount of tokens
    _txhash = token_agent.transfer(amount=locked_tokens,
                                   target_address=staker_account,
                                   sender_address=testerchain.etherbase_account)

    # Mock Powerup consumption (Staker)
    testerchain.transacting_power = TransactingPower(account=staker_account)
    testerchain.transacting_power.activate()

    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    staker = Staker(checksum_address=staker_account, is_me=True, registry=test_registry)
    staker.initialize_stake(amount=NU(locked_tokens, 'NuNit'),
                            lock_periods=token_economics.minimum_locked_periods)
    assert staker.locked_tokens(periods=1) == locked_tokens

    # The staker hasn't set a worker yet
    assert BlockchainInterface.NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.set_worker(staker_address=staker_account,
                                       worker_address=worker_account)

    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(worker_address=worker_account)

    ###### END OF STAKING ESCROW STUFF ####

    bob_account = testerchain.bob_account

    investigator = Investigator(registry=test_registry, checksum_address=bob_account)
    ursula = mock_ursula(testerchain, worker_account)

    # Let's create a bad cfrag
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)

    assert not investigator.was_this_evidence_evaluated(evidence)
    bobby_old_balance = investigator.token_balance

    # Mock Powerup consumption (Bob)
    testerchain.transacting_power = TransactingPower(account=bob_account)
    testerchain.transacting_power.activate()

    investigator.request_evaluation(evidence=evidence)

    assert investigator.was_this_evidence_evaluated(evidence)
    investigator_reward = investigator.token_balance - bobby_old_balance

    assert investigator_reward > 0
    assert investigator_reward == slashing_economics.base_penalty / slashing_economics.reward_coefficient
    assert staker.locked_tokens(periods=1) < locked_tokens
