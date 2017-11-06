from twisted.python.filepath import FilePath
from twisted.internet.ssl import PrivateCertificate, KeyPair, DN


def getCAPrivateCert():
    privatePath = FilePath(b"ca-private-cert.pem")
    if privatePath.exists():
        return PrivateCertificate.loadPEM(privatePath.getContent())
    else:
        caKey = KeyPair.generate(size=4096)
        caCert = caKey.selfSignedCert(1, CN="the-authority")
        privatePath.setContent(caCert.dumpPEM())
        return caCert


def clientCertFor(name):
    signingCert = getCAPrivateCert()
    clientKey = KeyPair.generate(size=4096)
    csr = clientKey.requestObject(DN(CN=name), "sha1")
    clientCert = signingCert.signRequestObject(
        csr, serialNumber=1, digestAlgorithm="sha1")
    return PrivateCertificate.fromCertificateAndKeyPair(clientCert, clientKey)


def and_generate():
    name = "llamas"
    pem = clientCertFor(name.encode("utf-8")).dumpPEM()
    FilePath(name.encode("utf-8") + b".client.private.pem").setContent(pem)
    return pem