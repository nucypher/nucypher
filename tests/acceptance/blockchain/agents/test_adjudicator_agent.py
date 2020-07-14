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
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.blockchain.eth.actors import NucypherTokenActor, Staker
from nucypher.blockchain.eth.agents import AdjudicatorAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.signing import SignatureStamp
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def mock_ursula(testerchain, account, mocker):
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


def test_adjudicator_slashes(agency,
                             testerchain,
                             mock_ursula_reencrypts,
                             token_economics,
                             test_registry,
                             mock_transacting_power_activation,
                             mocker):

    staker_account = testerchain.staker_account(0)
    worker_account = testerchain.ursula_account(0)

    ##### STAKING ESCROW STUFF #####

    token_agent, staking_agent, _policy_agent = agency

    locked_tokens = token_economics.minimum_allowed_locked * 5

    mock_transacting_power_activation(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    # The staker receives an initial amount of tokens
    _txhash = token_agent.transfer(amount=locked_tokens,
                                   target_address=staker_account,
                                   sender_address=testerchain.etherbase_account)

    mock_transacting_power_activation(account=staker_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    staker = Staker(checksum_address=staker_account, is_me=True, registry=test_registry)
    staker.initialize_stake(amount=NU(locked_tokens, 'NuNit'),
                            lock_periods=token_economics.minimum_locked_periods)
    assert staker.locked_tokens(periods=1) == locked_tokens

    # The staker hasn't bond a worker yet
    assert NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.bond_worker(staker_address=staker_account,
                                        worker_address=worker_account)

    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(worker_address=worker_account)

    ###### END OF STAKING ESCROW STUFF ####

    adjudicator_agent = AdjudicatorAgent(registry=test_registry)
    bob_account = testerchain.bob_account
    bobby = NucypherTokenActor(checksum_address=bob_account, registry=test_registry)
    ursula = mock_ursula(testerchain, worker_account, mocker=mocker)

    # Let's create a bad cfrag
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)

    assert not adjudicator_agent.was_this_evidence_evaluated(evidence)
    bobby_old_balance = bobby.token_balance

    mock_transacting_power_activation(account=bob_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    adjudicator_agent.evaluate_cfrag(evidence=evidence, sender_address=bob_account)

    assert adjudicator_agent.was_this_evidence_evaluated(evidence)
    investigator_reward = bobby.token_balance - bobby_old_balance

    assert investigator_reward > 0
    assert investigator_reward == token_economics.base_penalty / token_economics.reward_coefficient
    assert staker.locked_tokens(periods=1) < locked_tokens
