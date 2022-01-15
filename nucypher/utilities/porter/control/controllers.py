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

from nucypher.control.controllers import CLIController
from nucypher.control.emitters import StdoutEmitter


class PorterCLIController(CLIController):

    _emitter_class = StdoutEmitter

    def __init__(self,
                 interface: 'PorterInterface',
                 *args,
                 **kwargs):
        super().__init__(interface=interface, *args, **kwargs)

    def _perform_action(self, *args, **kwargs) -> dict:
        try:
            response_data = super()._perform_action(*args, **kwargs)
        finally:
            self.log.debug(f"Finished action '{kwargs['action']}', stopping {self.interface.implementer}")
            self.interface.implementer.disenchant()
        return response_data
