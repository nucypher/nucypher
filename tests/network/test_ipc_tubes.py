import pytest_twisted
from twisted.internet import reactor

from nucypher.crypto.cone_of_silence import InsideTheCone, OutsideTheCone

@pytest_twisted.inlineCallbacks
def test_speaking_across_the_cone():

    called_inside = []

    @InsideTheCone('./the-wire')
    def foo(message):
        return f"we foo'd this: {message}".encode()

    # @OutsideTheCone('./the-wire')
    # def foo(message):
    #     return f"we foo'd this: {message}".encode()

    d = foo(b'llamas')

    yield d
    assert False


