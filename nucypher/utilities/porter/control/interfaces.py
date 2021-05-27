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
from typing import List

from nucypher.control.interfaces import ControlInterface, attach_schema
from nucypher.utilities.porter.control.specifications import porter_schema


class PorterInterface(ControlInterface):
    def __init__(self, porter: 'Porter' = None, *args, **kwargs):
        super().__init__(implementer=porter, *args, **kwargs)

    #
    # Alice Endpoints
    #
    @attach_schema(porter_schema.AliceGetUrsulas)
    def get_ursulas(self,
                    quantity: int,
                    duration_periods: int,
                    exclude_ursulas: List[str],
                    include_ursulas: List[str]) -> dict:
        pass

    @attach_schema(porter_schema.AlicePublishTreasureMap)
    def publish_treasure_map(self,
                             treasure_map: bytes,
                             bob_encrypting_key: bytes) -> dict:
        pass

    @attach_schema(porter_schema.AliceRevoke)
    def revoke(self) -> dict:
        pass

    #
    # Bob Endpoints
    #
    @attach_schema(porter_schema.BobGetTreasureMap)
    def get_treasure_map(self,
                         treasure_map_id: bytes,
                         bob_encrypting_key: bytes) -> dict:
        pass

    @attach_schema(porter_schema.BobExecWorkOrder)
    def exec_work_order(self,
                        ursula: str,
                        work_order: bytes) -> dict:
        pass
