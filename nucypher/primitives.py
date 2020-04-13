class VersionedBytes:

    def __new__(cls, *args, **kwargs):
        """
        When instantiating a specific version of a versioned Bytestring,
        we want to automatically instantiate the latest version without
        requiring implementers to have to deal with any of this.

        If we are instantiating a specificly versioned class, allow for that also
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
    def __get_class(cls, klass, version):
        v = int.from_bytes(version, 'big')

        if getattr(klass, 'version', None) == v:
            return klass

        versioned_subclasses = VersionedBytes.__get_versioned_subclasses(klass)
        try:
            outclass = next(iter([c for c in versioned_subclasses if c.version == v]))
        except StopIteration:
            # if we can't find the right version, just return the base class.
            return klass
        return outclass

    @classmethod
    def parse_version(cls, some_bytes):
        version_bytes = some_bytes[:2]
        return VersionedBytes.__get_class(cls, version_bytes), some_bytes[2:]

    def add_version(self, some_bytes):
        return (self.version).to_bytes(2, 'big') + some_bytes
