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
from web3 import Web3

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU, Stake
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.skip()
def test_stake(testerchain, application_economics, agency, test_registry):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    class FakeUrsula:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

        burner_wallet = Web3().eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)
        checksum_address = burner_wallet.address
        staking_agent = staking_agent
        token_agent = token_agent
        blockchain = testerchain

    ursula = FakeUrsula()
    stake = Stake(checksum_address=ursula.checksum_address,
                  first_locked_period=1,
                  final_locked_period=100,
                  value=NU(100, 'NU'),
                  index=0,
                  staking_agent=staking_agent,
                  economics=application_economics)

    assert stake.value, 'NU' == NU(100, 'NU')

    assert isinstance(stake.time_remaining(), int)      # seconds
    slang_remaining = stake.time_remaining(slang=True)  # words
    assert isinstance(slang_remaining, str)


@pytest.mark.skip()
def test_stake_equality(application_economics, get_random_checksum_address, mocker):
    address = get_random_checksum_address()
    a_different_address = get_random_checksum_address()

    mock_agent = mocker.Mock(contract_address=a_different_address)

    stake = Stake(checksum_address=address,
                  first_locked_period=1,
                  final_locked_period=2,
                  value=NU(100, 'NU'),
                  index=0,
                  staking_agent=mock_agent,
                  economics=application_economics)

    assert stake == stake

    duck_stake = mocker.Mock(index=0,
                             value=NU(100, 'NU'),
                             first_locked_period=1,
                             final_locked_period=2,
                             staker_address=address,
                             staking_agent=mock_agent)
    assert stake == duck_stake

    a_different_stake = Stake(checksum_address=address,
                              first_locked_period=0,
                              final_locked_period=2,
                              value=NU(100, 'NU'),
                              index=1,
                              staking_agent=mock_agent,
                              economics=application_economics)

    assert stake != a_different_stake

    undercover_agent = mocker.Mock(contract_address=address)
    another_different_stake = Stake(checksum_address=a_different_address,
                                    first_locked_period=1,
                                    final_locked_period=2,
                                    value=NU(100, 'NU'),
                                    index=0,
                                    staking_agent=undercover_agent,
                                    economics=application_economics)

    assert stake != another_different_stake


@pytest.mark.skip()
def test_stake_integration(stakers):
    staker = list(stakers)[1]
    stakes = staker.stakes
    assert stakes

    stake = stakes[0]
    stake.sync()

    blockchain_stakes = staker.application_agent.get_all_stakes(staker_address=staker.checksum_address)

    stake_info = (stake.first_locked_period, stake.final_locked_period, int(stake.value))
    published_stake_info = list(blockchain_stakes)[0]
    assert stake_info == published_stake_info
    assert stake_info == stake.to_stake_info()
    assert stake.status() == Stake.Status.DIVISIBLE
