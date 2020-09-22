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

import requests
import socket

NodeSeemsToBeDown = (requests.exceptions.ConnectionError,
                     requests.exceptions.ReadTimeout,
                     requests.exceptions.ConnectTimeout,
                     socket.gaierror,
                     ConnectionRefusedError)



class TreasureMapReceptionException(BaseException):
        status_code = NotImplemented
        msg = NotImplemented
        log_message = NotImplemented


class TreasureMapReceptionExceptions:


    class InvalidTreasureMapSignature(TreasureMapReceptionException):

        status_code = 401
        msg = "This TreasureMap's HRAC is not properly signed."
        log_message = "Bad TreasureMap HRAC Signature; not storing {}"

    class AlreadyHaveThisTreasureMap(TreasureMapReceptionException):

        status_code = 303
        msg = "Already have this map."
        log_message = None

    class TreasureMapAddressMismatch(TreasureMapReceptionException):

        status_code = 409
        msg = "Can't save a TreasureMap with this ID from you.", 409
        log_message = None


    class TreasureMapBadID(TreasureMapReceptionException):

        status_code = 402
        log_message = "Bad TreasureMap ID; not storing {}"
        msg = "This TreasureMap doesn't match a paid Policy."
