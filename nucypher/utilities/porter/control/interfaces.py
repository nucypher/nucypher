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

from umbral.keys import UmbralPublicKey

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
        # Steps (analogous to nucypher.character.control.interfaces):
        # 1. creation of relevant objects / setup
        # 2. call self.implementer.some_function() i.e. Porter learner has an associated function to call
        # 3. create response
        pass

    @attach_schema(porter_schema.AlicePublishTreasureMap)
    def publish_treasure_map(self,
                             treasure_map: bytes,
                             bob_encrypting_key: bytes) -> dict:
        bob_enc_key = UmbralPublicKey.from_bytes(bob_encrypting_key)
        self.implementer.publish_treasure_map(treasure_map_bytes=treasure_map,
                                              bob_encrypting_key=bob_enc_key)
        return {}

    @attach_schema(porter_schema.AliceRevoke)
    def revoke(self) -> dict:
        # Steps (analogous to nucypher.character.control.interfaces):
        # 1. creation of objects / setup
        # 2. call self.implementer.some_function() i.e. Porter learner has an associated function to call
        # 3. create response
        pass

    #
    # Bob Endpoints
    #
    @attach_schema(porter_schema.BobGetTreasureMap)
    def get_treasure_map(self,
                         treasure_map_id: str,
                         bob_encrypting_key: bytes) -> dict:
        bob_enc_key = UmbralPublicKey.from_bytes(bob_encrypting_key)
        treasure_map = self.implementer.get_treasure_map(map_identifier=treasure_map_id,
                                                         bob_encrypting_key=bob_enc_key)
        response_data = {'treasure_map': treasure_map}
        return response_data

    @attach_schema(porter_schema.BobExecWorkOrder)
    def exec_work_order(self,
                        ursula: str,
                        work_order: bytes) -> dict:
        # Steps (analogous to nucypher.character.control.interfaces):
        # 1. creation of relevant objects / setup
        # 2. call self.implementer.some_function() i.e. Porter learner has an associated function to call
        # 3. create response
        pass
