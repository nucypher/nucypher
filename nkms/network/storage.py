from kademlia.storage import ForgetfulStorage


class SeedOnlyStorage(ForgetfulStorage):

    def __setitem__(self, key, value):
        pass