from nucypher.crypto.cone_of_silence import InsideTheCone, OutsideTheCone
from tubes.listening import Listener

from tubes.tube import series, tube
from twisted.internet import endpoints, reactor
from twisted.internet.defer import succeed
from tubes.protocol import flowFromEndpoint, flowFountFromEndpoint
import sys

try:
    INSIDE = bool(sys.argv[1])
except IndexError:
    INSIDE = False



run_in_the_cone_of_silence = InsideTheCone if INSIDE else OutsideTheCone



@run_in_the_cone_of_silence('./the-wire')
def foo(message):
    return f"we foo'd this: {message}".encode()


@run_in_the_cone_of_silence("./bar")
def bar():
    assert False


def make_assertion(result):
    assert False


if not INSIDE:
    b = foo(b"this goes over the wire")
    b.addCallback(make_assertion)

reactor.run()