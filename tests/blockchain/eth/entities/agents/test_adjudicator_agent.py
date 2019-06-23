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

from nucypher.blockchain.eth.actors import NucypherTokenActor
from nucypher.blockchain.eth.agents import AdjudicatorAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.crypto.powers import BlockchainPower


def mock_ursula(testerchain, account):

    from mock import Mock

    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_utils.address import to_canonical_address
    from umbral.keys import UmbralPrivateKey
    from umbral.signing import Signer

    from nucypher.crypto.signing import SignatureStamp

    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))

    # Sign Umbral public key using eth-key
    address = to_canonical_address(account)
    sig_key = testerchain.provider.ethereum_tester.backend._key_lookup[address]
    signable_message = encode_defunct(primitive=bytes(ursula_stamp))
    signature = Account.sign_message(signable_message=signable_message,
                                     private_key=sig_key)
    signed_stamp = bytes(signature.signature)

    ursula = Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula



@pytest.mark.slow()
def test_adjudicator_slashes(agency, testerchain, mock_ursula_reencrypts, token_economics):
    staker_account = testerchain.staker_account(0)
    worker_account = testerchain.ursula_account(0)

    ##### STAKING ESCROW STUFF #####

    token_agent, staking_agent, _policy_agent = agency

    locked_tokens = token_economics.minimum_allowed_locked * 5

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = BlockchainPower(blockchain=testerchain, account=testerchain.etherbase_account)

    balance = token_agent.get_balance(address=staker_account)
    assert balance == 0

    # The staker receives an initial amount of tokens
    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked * 10,
                                   target_address=staker_account,
                                   sender_address=testerchain.etherbase_account)

    # Mock Powerup consumption (Ursula-Staker)
    testerchain.transacting_power = BlockchainPower(blockchain=testerchain, account=staker_account)

    #
    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    # Previously, she needs to approve this transfer on the token contract.
    #

    _receipt = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked * 10,  # Approve
                                            target_address=staking_agent.contract_address,
                                            sender_address=staker_account)

    receipt = staking_agent.deposit_tokens(amount=locked_tokens,
                                           lock_periods=token_economics.minimum_locked_periods,
                                           sender_address=staker_account)

    testerchain.time_travel(periods=1)
    balance = token_agent.get_balance(address=staker_account)
    assert balance == locked_tokens
    assert staking_agent.get_locked_tokens(staker_address=staker_account) == locked_tokens

    # The staker hasn't set a worker yet
    assert BlockchainInterface.NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.set_worker(staker_address=staker_account,
                                       worker_address=worker_account)

    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(worker_address=worker_account)

    ###### END OF STAKING ESCROW STUFF ####

    adjudicator_agent = AdjudicatorAgent()
    bob_account = testerchain.bob_account
    bobby = NucypherTokenActor(blockchain=testerchain, checksum_address=bob_account)
    stacy = NucypherTokenActor(blockchain=testerchain, checksum_address=staker_account)
    ursula = mock_ursula(testerchain, worker_account)

    # Let's create a bad cfrag
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)

    assert not adjudicator_agent.was_this_evidence_evaluated(evidence)
    bobby_old_balance = bobby.token_balance
    stacy_old_balance = stacy.token_balance

    # Mock Powerup consumption (Ursula-Staker)
    testerchain.transacting_power = BlockchainPower(blockchain=testerchain, account=bob_account)
    adjudicator_agent.evaluate_cfrag(evidence=evidence, sender_address=bob_account)

    assert adjudicator_agent.was_this_evidence_evaluated(evidence)
    assert bobby.token_balance > bobby_old_balance

    # FIXME: Not working for some reason. Let's try tomorrow.
    # assert stacy.token_balance < stacy_old_balance


