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

from bytestring_splitter import BytestringSplitter, BytestringKwargifier, StructureChecksumMixin, VersioningMixin


BYTESTRING_REGISTRY = {}


class NCBytestringSplitter(StructureChecksumMixin, VersioningMixin, BytestringSplitter):
    """
    Renders bytestrings as: <checksum (4 bytes)><version (2 bytes)><bytestring content>
    """

    def validate_checksum(self, *args, **kwargs):
        # until https://github.com/nucypher/bytestringSplitter/pull/34 is merged and deployed
        return self.get_metadata(args[0])['checksum'] == self.generate_checksum()

class NucypherBSSKwargifier(NCBytestringSplitter, BytestringKwargifier):

    def __init__(self, byteclass, *args, **kwargs):
        super().__init__(byteclass, *args, **kwargs)
        BYTESTRING_REGISTRY[self.generate_checksum()] = byteclass
