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

# Connectivity
class NoConnectionToChain(RuntimeError):
    """Raised when a node does not have an associated provider for a chain."""

    def __init__(self, chain: int, *args, **kwargs):
        self.chain = chain
        super().__init__(*args, **kwargs)


# Context Variable
class RequiredContextVariable(Exception):
    """No value provided for context variable"""


class InvalidContextVariableData(Exception):
    """Context variable could not be processed"""


class ContextVariableVerificationFailed(Exception):
    """Issue with using the provided context variable."""


# Conditions
class InvalidCondition(ValueError):
    """Invalid value for condition."""


class ConditionEvaluationFailed(Exception):
    """Could not evaluate condition."""


class RPCExecutionFailed(ConditionEvaluationFailed):
    """Raised when an exception is raised from an RPC call."""
