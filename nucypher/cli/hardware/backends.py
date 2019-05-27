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


from abc import ABC, abstractmethod


class TrustedDevice(ABC):
    """
    An Abstract Base Class for implementing wallet-like functions for stakers
    utilizing trusted hardware devices (e.g. trezor).
    This class specifies a few basic functions required for staking on the
    NuCypher network.
    """

    @abstractmethod
    def sign_message(self):
        pass

    @abstractmethod
    def verify_message(self):
        pass
