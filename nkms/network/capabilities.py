from contextlib import suppress

from bidict import bidict
_capability_mapping = bidict()


class ServerCapability(object):

    prohibits_storage = False

    @staticmethod
    def stringify(capability):
        try:
            string_repr = _capability_mapping.inv[capability.__class__]
        except KeyError:
            string_repr = _capability_mapping.inv[capability]

        return string_repr

    @staticmethod
    def from_name(capability_name, *args, **kwargs):
        capability_class = _capability_mapping[capability_name]
        return capability_class(*args, **kwargs)


class SeedOnly(ServerCapability):
    prohibits_storage = True


# What follows is a rather shameful hack to provide compatibity with kademlia's serialization, which uses umsgpack.
# Obviously by iterating only locals we prevent users from defining capabilities elsehwere.
# Other, somewhat better ways of doing this:
# * use a decorator-registry.
# * monkeypatch rpcudp.protocol.__getaddr__.func to allow a serialization method to be injected
# * Override __getaddr_ completely
for l in list(locals().values()):
    with suppress(TypeError):
        if issubclass(l, ServerCapability):
            _capability_mapping[l.__name__] = l

