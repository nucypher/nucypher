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

MAX_NUNIT_ERROR = 10 * 1e-18  # 2 decimal places


def commit_to_next_period(staking_agent, ursulas_tpowers):
    for ursula_tpower in ursulas_tpowers:
        staking_agent.commit_to_next_period(transacting_power=ursula_tpower)


def prepare_staker(origin_tpower, staking_agent, token_agent, token_economics, ursula, ursula_tpower, amount, lock_periods=None):
    if not lock_periods:
        lock_periods = 100 * token_economics.maximum_rewarded_periods

    # Prepare one staker
    _txhash = token_agent.transfer(amount=amount,
                                   target_address=ursula,
                                   transacting_power=origin_tpower)
    _txhash = token_agent.approve_transfer(amount=amount,
                                           spender_address=staking_agent.contract_address,
                                           transacting_power=ursula_tpower)
    _txhash = staking_agent.deposit_tokens(amount=amount,
                                           lock_periods=lock_periods,
                                           transacting_power=ursula_tpower,
                                           staker_address=ursula)
    _txhash = staking_agent.bond_worker(transacting_power=ursula_tpower, worker_address=ursula)
    _txhash = staking_agent.set_restaking(transacting_power=ursula_tpower, value=False)
