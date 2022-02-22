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

from nucypher_core.umbral import SecretKeyFactory, Signer

from nucypher.blockchain.eth.actors import NucypherTokenActor
from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NucypherTokenAgent
)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.crypto.signing import SignatureStamp


def mock_ursula(testerchain, account, mocker):
    ursula_privkey = SecretKeyFactory.random()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.public_key(),
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


@pytest.mark.skip("David, send help!")
def test_adjudicator_slashes(agency,
                             testerchain,
                             #mock_ursula_reencrypts,
                             application_economics,
                             test_registry,
                             mocker):

    staker_account = testerchain.stake_provider_account(0)
    worker_account = testerchain.ursula_account(0)

    ##### STAKING ESCROW STUFF #####

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    locked_tokens = application_economics.min_authorization * 5

    # The staker receives an initial amount of tokens
    tpower = TransactingPower(account=testerchain.etherbase_account, signer=Web3Signer(testerchain.client))
    _txhash = token_agent.transfer(amount=locked_tokens,
                                   target_address=staker_account,
                                   transacting_power=tpower)

    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    tpower = TransactingPower(account=staker_account, signer=Web3Signer(testerchain.client))
    staker = Staker(domain=TEMPORARY_DOMAIN,
                    registry=test_registry,
                    transacting_power=tpower)

    staker.initialize_stake(amount=NU(locked_tokens, 'NuNit'),
                            lock_periods=application_economics.min_operator_seconds)
    assert staker.locked_tokens(periods=1) == locked_tokens

    # The staker hasn't bond a worker yet
    assert NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.bond_worker(transacting_power=tpower, operator_address=worker_account)

    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(operator_address=worker_account)

    ###### END OF STAKING ESCROW STUFF ####

    adjudicator_agent = AdjudicatorAgent(registry=test_registry)
    bob_account = testerchain.bob_account
    bobby = NucypherTokenActor(checksum_address=bob_account,
                               domain=TEMPORARY_DOMAIN,
                               registry=test_registry)
    ursula = mock_ursula(testerchain, worker_account, mocker=mocker)

    # Let's create a bad cfrag
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)

    assert not adjudicator_agent.was_this_evidence_evaluated(evidence)
    bobby_old_balance = bobby.token_balance
    bob_tpower = TransactingPower(account=bob_account, signer=Web3Signer(testerchain.client))

    adjudicator_agent.evaluate_cfrag(evidence=evidence, transacting_power=bob_tpower)

    assert adjudicator_agent.was_this_evidence_evaluated(evidence)
    investigator_reward = bobby.token_balance - bobby_old_balance

    assert investigator_reward > 0
    assert investigator_reward == application_economics.base_penalty / application_economics.reward_coefficient
    assert staker.locked_tokens(periods=1) < locked_tokens
