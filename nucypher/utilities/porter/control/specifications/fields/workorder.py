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

from nucypher.control.specifications.fields import Base64BytesRepresentation
from nucypher.policy.orders import WorkOrder as WorkOrderClass


class WorkOrder(Base64BytesRepresentation):
    def _serialize(self, value: WorkOrderClass, attr, obj, **kwargs):
        return super()._serialize(value.payload(), attr, obj, **kwargs)


class WorkOrderResult(Base64BytesRepresentation):
    pass
