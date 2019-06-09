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

import maya


def epoch_to_period(epoch: int) -> int:
    from nucypher.blockchain.economics import TokenEconomics
    period = epoch // int(TokenEconomics.seconds_per_period)
    return period


def datetime_to_period(datetime: maya.MayaDT) -> int:
    """Converts a MayaDT instance to a period number."""
    future_period = epoch_to_period(epoch=datetime.epoch)
    return int(future_period)


def datetime_at_period(period: int) -> maya.MayaDT:
    """Returns the datetime object at a given period, future, or past."""

    now = maya.now()
    current_period = datetime_to_period(datetime=now)
    delta_periods = period - current_period

    # +
    if delta_periods:
        target_period = now + maya.timedelta(days=delta_periods)

    # -
    else:
        target_period = now - maya.timedelta(days=delta_periods)

    return target_period


def calculate_period_duration(future_time: maya.MayaDT) -> int:
    """Takes a future MayaDT instance and calculates the duration from now, returning in periods"""
    future_period = datetime_to_period(datetime=future_time)
    current_period = datetime_to_period(datetime=maya.now())
    periods = future_period - current_period
    return periods
