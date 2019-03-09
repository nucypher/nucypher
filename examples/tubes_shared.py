from tubes.listening import Listener

from tubes.tube import series, tube
from twisted.internet import endpoints, reactor

from tubes.protocol import flowFromEndpoint, flowFountFromEndpoint
import sys

try:
    INSIDE = bool(sys.argv[1])
except IndexError:
    INSIDE = False



@tube
class InsideTheCone:

    def __init__(self, socket_path):
        # self.endpoint = endpoints.UNIXServerEndpoint(reactor, socket_path, mode=0o600)
        # d = flowFountFromEndpoint(self.endpoint)
        # d.addCallback(self.llamas)
        return

    def __call__(self, f):
        self.func = f
        self.endpoint = endpoints.UNIXServerEndpoint(reactor, f.__qualname__, mode=0o600)
        d = flowFountFromEndpoint(self.endpoint)
        d.addCallback(self.llamas)
        return f

    def listener(self, flow):
        flow.fount.flowTo(series(self)).flowTo(flow.drain)

    def llamas(self, caller_fount):
        caller_fount.flowTo(Listener(self.listener))

    def received(self, line):
        yield self.func(line)


@tube
class OutsideTheCone:
    def __init__(self, socket_path):
        # self.endpoint = endpoints.UNIXClientEndpoint(reactor, socket_path, timeout=2)
        return

    def __call__(self, f):
        # Send call across the wire.
        self.endpoint = endpoints.UNIXClientEndpoint(reactor, f.__qualname__, timeout=2)
        self.func = f
        return self._call_across_wire

    def _call_across_wire(self, *args, **kwargs):
        d = flowFromEndpoint(self.endpoint).addCallback(self._handle_flow, *args, **kwargs).addErrback(self._handle_errors)
        return d

    def _handle_flow(self, flow, line, *args, **kwargs):
        flow.fount.flowTo(series(self))
        flow.drain.receive(line)

    def _handle_errors(self, failure):
        assert False

    def received(self, line):
        return line

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