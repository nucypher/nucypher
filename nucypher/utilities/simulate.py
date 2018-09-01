from twisted.internet import protocol


class UrsulaProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, command):
        self.command = command

    def connectionMade(self):
        print("connectionMade!")
        self.transport.closeStdin()   # tell them we're done

    def outReceived(self, data):
        print(data)

    def errReceived(self, data):
        print(data)

    def inConnectionLost(self):
        print("inConnectionLost! stdin is closed! (we probably did it)")

    def outConnectionLost(self):
        print("outConnectionLost! The child closed their stdout!")

    def errConnectionLost(self):
        print("errConnectionLost! The child closed their stderr.")

    def processEnded(self, status_object):
        print("processEnded, status %d" % status_object.value.exitCode)
        print("quitting")
