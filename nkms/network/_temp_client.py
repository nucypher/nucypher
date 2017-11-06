from twisted.python.filepath import FilePath
from twisted.internet.endpoints import SSL4ClientEndpoint
from twisted.internet.ssl import (
    PrivateCertificate, Certificate, optionsForClientTLS)
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.task import react
from twisted.internet.protocol import Protocol, Factory

from nkms.network import generate_certs


class SendAnyData(Protocol):
    def connectionMade(self):
        self.deferred = Deferred()
        self.transport.write(b"HELLO\r\n")
    def connectionLost(self, reason):
        self.deferred.callback(None)


@inlineCallbacks
def main(reactor):
    pem = generate_certs.and_generate()
    caPem = FilePath(b"ca-private-cert.pem").getContent()
    clientEndpoint = SSL4ClientEndpoint(
        reactor, u"localhost", 4321,
        optionsForClientTLS(u"the-authority", Certificate.loadPEM(caPem),
                            PrivateCertificate.loadPEM(pem)),
    )
    clientEndpoint = SSL4ClientEndpoint(
        reactor, u"localhost", 4321,
        optionsForClientTLS(u"the-authority", Certificate.loadPEM(caPem),
                            PrivateCertificate.loadPEM(pem)),
    )
    proto = yield clientEndpoint.connect(Factory.forProtocol(SendAnyData))
    yield proto.deferred

what_happened = react(main)
print(what_happened)