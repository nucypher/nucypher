from twisted.python.filepath import FilePath
from twisted.internet.endpoints import SSL4ServerEndpoint
from twisted.internet.ssl import PrivateCertificate, Certificate
from twisted.internet.defer import Deferred
from twisted.internet.task import react
from twisted.internet.protocol import Protocol, Factory

class ReportWhichClient(Protocol):
    def dataReceived(self, data):
        peerCertificate = Certificate.peerFromTransport(self.transport)
        print(peerCertificate.getSubject().commonName.decode('utf-8'))
        self.transport.loseConnection()

def main(reactor):
    pemBytes = FilePath(b"ca-private-cert.pem").getContent()
    certificateAuthority = Certificate.loadPEM(pemBytes)
    myCertificate = PrivateCertificate.loadPEM(pemBytes)
    serverEndpoint = SSL4ServerEndpoint(
        reactor, 4321, myCertificate.options(certificateAuthority)
    )
    serverEndpoint.listen(Factory.forProtocol(ReportWhichClient))
    return Deferred()

react(main, [])