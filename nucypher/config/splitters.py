from bytestring_splitter import BytestringSplitter, BytestringKwargifier, StructureChecksumMixin, VersioningMixin


class NCBytestringSplitter(StructureChecksumMixin, VersioningMixin, BytestringSplitter):
    """
    Renders bytestrings as: <checksum (4 bytes)><version (2 bytes)><bytestring content>
    """

class NucypherBSSKwargifier(NCBytestringSplitter, BytestringKwargifier):
    pass