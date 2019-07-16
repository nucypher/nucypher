"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os

from urllib.parse import urlparse

from eth_utils import is_checksum_address

from bytestring_splitter import VariableLengthBytestring

from twisted.internet import reactor
from twisted.application import internet, service
from twisted.python.threadpool import ThreadPool
from twisted.web.static import File
from twisted.web import server
from twisted.internet import ssl

from hendrix.deploy.base import HendrixDeploy
from hendrix.deploy.tls import HendrixDeployTLS
from hendrix.facilities.services import HendrixTCPServiceWithTLS, HendrixService, ThreadPoolService, HendrixTCPService
from hendrix.facilities.resources import HendrixResource, NamedResource



from nucypher.config.constants import STATICS_DIR


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


def parse_node_uri(uri: str):
    from nucypher.config.characters import UrsulaConfiguration

    if '@' in uri:
        checksum_address, uri = uri.split("@")
        if not is_checksum_address(checksum_address):
            raise ValueError("{} is not a valid checksum address.".format(checksum_address))
    else:
        checksum_address = None  # federated

    parsed_uri = urlparse(uri)

    if not parsed_uri.scheme:
        try:
            parsed_uri = urlparse('https://'+uri)
        except Exception:
            raise  # TODO: Do we need even deeper handling/validation here?

    if not parsed_uri.scheme == "https":
        raise ValueError("Invalid teacher scheme or protocol. Is the hostname prefixed with 'https://' ?")

    hostname = parsed_uri.hostname
    port = parsed_uri.port or UrsulaConfiguration.DEFAULT_REST_PORT
    return hostname, port, checksum_address


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        loopback, localhost = '127.0.0.1', 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b':', 1)
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    @property
    def uri(self):
        return u"{}:{}".format(self.host, self.port)

    @property
    def formal_uri(self):
        return u"{}://{}".format('https', self.uri)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)


class HendrixResourceWithStatics(HendrixResource):

    def getChild(self, name, request):

        path = name.decode('utf-8')
        if path in self.children:
            return self.children[path]

        return super().getChild(name, request)


class HendrixTCPServiceWithTLSAndStatics(HendrixTCPServiceWithTLS):

    def __init__(self, port, private_key, cert,
        context_factory=None,
        context_factory_kwargs=None,
        application=None,
        threadpool=None
    ):
        hxresource = HendrixResourceWithStatics(

            reactor, threadpool, application)

        child = File(STATICS_DIR)
        child.namespace = 'statics'
        hxresource.putNamedChild(child)
        site = server.Site(hxresource)

        context_factory = context_factory or ssl.DefaultOpenSSLContextFactory
        context_factory_kwargs = context_factory_kwargs or {}

        self.tls_context = context_factory(
            private_key,
            cert,
            **context_factory_kwargs
        )
        internet.SSLServer.__init__(
            self,
            port,  # integer port
            site,  # our site object, see the web howto
            contextFactory=self.tls_context
        )


class HendrixServiceWithStatics(HendrixService):

    def __init__(
            self,
            application,
            threadpool=None,
            resources=None,
            services=None,
            loud=False):
        service.MultiService.__init__(self)

        # Create, start and add a thread pool service, which is made available
        # to our WSGIResource within HendrixResource
        if not threadpool:
            self.threadpool = ThreadPool(name="HendrixService")
        else:
            self.threadpool = threadpool

        reactor.addSystemEventTrigger('after', 'shutdown', self.threadpool.stop)
        ThreadPoolService(self.threadpool).setServiceParent(self)

        # create the base resource and add any additional static resources
        resource = HendrixResourceWithStatics(reactor, self.threadpool, application, loud=loud)
        if resources:
            resources = sorted(resources, key=lambda r: r.namespace)
            for res in resources:
                if hasattr(res, 'get_resources'):
                    for sub_res in res.get_resources():
                        resource.putNamedChild(sub_res)
                else:
                    resource.putNamedChild(res)

        self.site = server.Site(resource)


class HendrixDeployWithStatics(HendrixDeploy):

    def addHendrix(self):
        '''
        Instantiates a HendrixService with this object's threadpool.
        It will be added as a service later.
        '''
        self.hendrix = HendrixServiceWithStatics(
            self.application,
            threadpool=self.getThreadPool(),
            resources=self.resources,
            services=self.services,
            loud=self.options['loud']
        )
        if self.options["https_only"] is not True:
            self.hendrix.spawn_new_server(self.options['http_port'], HendrixTCPService)


class DeployTLSWithStatics(HendrixDeployTLS):

    def __init__(self, *args, **kwargs):
        self.wsgi_application = kwargs.get('options').get('wsgi')
        super().__init__(*args, **kwargs)

    def addSSLService(self):
        "adds a SSLService to the instaitated HendrixService"
        https_port = self.options['https_port']
        self.tls_service = HendrixTCPServiceWithTLSAndStatics(
            https_port, self.key, self.cert,
            context_factory=self.context_factory,
            context_factory_kwargs=self.context_factory_kwargs,
            application=self.wsgi_application,
            threadpool=self.hendrix.threadpool
        )

        self.tls_service.setServiceParent(self.hendrix)


def get_statics(filepath=None, namespace=None):

    child = File(filepath or STATICS_DIR)
    child.namespace = namespace or 'statics'
    return [child]
