class VersionedBytes:

    class NucypherNeedsUpdateException(BaseException):
        """This node cannot instantiate a class from data created by a newer version of NuCypher."""

    def __new__(cls, *args, **kwargs):
        """
        When instantiating a specific version of a versioned Bytestring,
        we want to automatically instantiate the latest version without
        requiring implementors to have to deal with any of this.

        If we are instantiating a specifically versioned class, allow for that also
        """

        if not hasattr(cls, 'version'):
            versioned_subclasses = VersionedBytes.__get_versioned_subclasses(cls)
            # take the highest
            cls = sorted(versioned_subclasses, key=lambda x: x.version)[-1]
        return super(VersionedBytes, cls).__new__(cls)

    @classmethod
    def __get_versioned_subclasses(cls, klass):
        return [cls for cls in klass.__subclasses__() if hasattr(cls, 'version')]

    @classmethod
    def __get_class(cls, klass, version_bytes):
        v = int.from_bytes(version_bytes, 'big')

        if getattr(klass, 'version', None) == v:
            return klass

        versioned_subclasses = VersionedBytes.__get_versioned_subclasses(klass)
        try:
            outclass = next(iter([c for c in versioned_subclasses if c.version == v]))
        except StopIteration:

            if len(versioned_subclasses) and v > 1:
                # We have received data that was clearly created by a newer version of Nucypher,
                # TODO:  I don't know exactly what to do here.
                # would a bob be receiving this?  Or an Alice?
                # Who needs to know about this?
                # can we notify the staker of a node that their Worker needs an update?

                raise VersionedBytes.NucypherNeedsUpdateException("This node is running outdated NuCypher code")

            # if we don't have versioned subclasses or the version == 1, it's just really soon.
            # lets not get ahead of ourselves, we can probably move on with life.
            return klass

        return outclass

    @classmethod
    def parse_version(cls, some_bytes):
        version_bytes = some_bytes[:2]
        return VersionedBytes.__get_class(cls, version_bytes), some_bytes[2:]

    def add_version(self, some_bytes):
        return (self.version).to_bytes(2, 'big') + some_bytes
