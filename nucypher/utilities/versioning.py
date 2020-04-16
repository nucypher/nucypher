class ByteVersioningMixin:

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
            versioned_subclasses = ByteVersioningMixin.__get_versioned_subclasses(cls)
            # take the highest
            cls = sorted(versioned_subclasses, key=lambda x: x.version)[-1]
        return super(ByteVersioningMixin, cls).__new__(cls)

    @classmethod
    def __get_versioned_subclasses(cls, klass):
        return [cls for cls in klass.__subclasses__() if hasattr(cls, 'version')]

    @classmethod
    def __get_class(cls, klass, version_bytes):
        v = int.from_bytes(version_bytes, 'big')

        if getattr(klass, 'version', None) == v:
            return klass

        versioned_subclasses = ByteVersioningMixin.__get_versioned_subclasses(klass)
        try:
            outclass = next(iter([c for c in versioned_subclasses if c.version == v]))
        except StopIteration:

            if len(versioned_subclasses) and 99 >= v > 1:
                # We have received data that was clearly created by a newer version of Nucypher,
                # TODO:  I don't know exactly what to do here.
                # would a bob be receiving this?  Or an Alice?
                # Who needs to know about this?
                # can we notify the staker of a node that their Worker needs an update?

                raise ByteVersioningMixin.NucypherNeedsUpdateException("This node is running outdated NuCypher code")

            # if the 1st two bytes aren't between 1 and 99, or if we have some weird broken data,
            # lets not get ahead of ourselves, we can probably move on with life.
            # return the base class and let it fail or succeed...
            return klass

        return outclass

    @classmethod
    def parse_version(cls, some_bytes):
        version_bytes = some_bytes[:2]
        output_class = ByteVersioningMixin.__get_class(cls, version_bytes)

        output_bytes = some_bytes if output_class is cls and not hasattr(cls, 'version') else some_bytes[2:]
        # if we got an unversioned base class, it means we probably could not parse a version
        # and we have some legacy pre-versioned data here.  Lets just let it fail or succeed
        # in whatever ensuing bytesplitter this data may encounter

        return output_class, output_bytes

    def prepend_version(self, some_bytes):
        return (self.version).to_bytes(2, 'big') + some_bytes
