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


from nucypher.blockchain.eth.utils import prettify_eth_amount


def paint_fee_rate_range(emitter, policy_agent):
    minimum, default, maximum = policy_agent.get_fee_rate_range()

    range_payload = f"""
Global fee Range:
    ~ Minimum ............ {prettify_eth_amount(minimum)}
    ~ Default ............ {prettify_eth_amount(default)}
    ~ Maximum ............ {prettify_eth_amount(maximum)}"""
    emitter.echo(range_payload)


def paint_min_rate(emitter, registry, policy_agent, staker_address):
    paint_fee_rate_range(emitter, policy_agent)
    minimum = policy_agent.min_fee_rate(staker_address)
    raw_minimum = policy_agent.raw_min_fee_rate(staker_address)

    rate_payload = f"""
Minimum acceptable fee rate (set by staker for their associated worker):
    ~ Previously set ....... {prettify_eth_amount(raw_minimum)}
    ~ Effective ............ {prettify_eth_amount(minimum)}"""
    emitter.echo(rate_payload)
