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

from nucypher.policy.conditions.lingo import ConditionLingo

CONDITIONS = [
        {
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "timelock"
        },
        {"operator": "and"},
        {
            "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
            "method": "timelock",
        },
    ]


def test_compound_condition_timelock():
    clingo = ConditionLingo.from_list(CONDITIONS)
    assert clingo.eval()


def test_condition_lingo_repr():
    clingo = ConditionLingo.from_list(CONDITIONS)
    clingo_string = f"{clingo}"
    assert f"{clingo.__class__.__name__}" in clingo_string
    assert f"id={clingo.id}" in clingo_string
    assert f"size={len(bytes(clingo))}" in clingo_string
