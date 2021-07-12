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
from typing import List, Optional

from eth_typing import ChecksumAddress
from nucypher.crypto.umbral_adapter import PublicKey

from nucypher.characters.control.specifications.fields import TreasureMap
from nucypher.control.interfaces import ControlInterface, attach_schema
from nucypher.utilities.porter.control.specifications import porter_schema


class PorterInterface(ControlInterface):
    def __init__(self, porter: 'Porter' = None, *args, **kwargs):
        super().__init__(implementer=porter, *args, **kwargs)
        # set federated/non-federated context for publish treasure map schema
        PorterInterface.publish_treasure_map._schema.context[TreasureMap.IS_FEDERATED_CONTEXT_KEY] = porter.federated_only

    #
    # Alice Endpoints
    #
    @attach_schema(porter_schema.AliceGetUrsulas)
    def get_ursulas(self,
                    quantity: int,
                    duration_periods: int,
                    exclude_ursulas: Optional[List[ChecksumAddress]] = None,
                    include_ursulas: Optional[List[ChecksumAddress]] = None) -> dict:
        ursulas_info = self.implementer.get_ursulas(quantity=quantity,
                                                    duration_periods=duration_periods,
                                                    exclude_ursulas=exclude_ursulas,
                                                    include_ursulas=include_ursulas)

        response_data = {
            "ursulas": ursulas_info
        }
        return response_data

    @attach_schema(porter_schema.AlicePublishTreasureMap)
    def publish_treasure_map(self,
                             treasure_map: bytes,
                             bob_encrypting_key: bytes) -> dict:
        bob_enc_key = PublicKey.from_bytes(bob_encrypting_key)
        self.implementer.publish_treasure_map(treasure_map_bytes=treasure_map,
                                              bob_encrypting_key=bob_enc_key)
        response_data = {'published': True}  # always True - if publish failed, an exception is raised by implementer
        return response_data

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
        bob_enc_key = PublicKey.from_bytes(bob_encrypting_key)
        treasure_map = self.implementer.get_treasure_map(map_identifier=treasure_map_id,
                                                         bob_encrypting_key=bob_enc_key)
        response_data = {'treasure_map': treasure_map}
        return response_data

    @attach_schema(porter_schema.BobExecWorkOrder)
    def exec_work_order(self,
                        ursula: ChecksumAddress,
                        work_order_payload: bytes) -> dict:
        work_order_result = self.implementer.exec_work_order(ursula_address=ursula,
                                                             work_order_payload=work_order_payload)
        response_data = {'work_order_result': work_order_result}
        return response_data
