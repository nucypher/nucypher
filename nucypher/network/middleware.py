"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import socket
import ssl

import requests
import time
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from twisted.logger import Logger
from umbral.cfrags import CapsuleFrag
from umbral.signing import Signature

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring


class RestMiddleware:
    log = Logger()

    def consider_arrangement(self, arrangement):
        node = arrangement.ursula
        response = requests.post("https://{}/consider_arrangement".format(node.rest_interface),
                                 bytes(arrangement),
                                 verify=node.certificate_filepath, timeout=2)

        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return response

    def get_certificate(self, host, port, timeout=3, retry_attempts: int = 3, retry_rate: int = 2,
                        current_attempt: int = 0):

        socket.setdefaulttimeout(timeout)  # Set Socket Timeout

        try:
            self.log.info("Fetching seednode {}:{} TLS certificate".format(host, port))
            seednode_certificate = ssl.get_server_certificate(addr=(host, port))

        except socket.timeout:
            if current_attempt == retry_attempts:
                message = "No Response from seednode {}:{} after {} attempts"
                self.log.info(message.format(host, port, retry_attempts))
                raise RuntimeError("No response from {}:{}".format(host, port))
            self.log.info("No Response from seednode {}. Retrying in {} seconds...".format(host, retry_rate))
            time.sleep(retry_rate)
            return self.get_certificate(host, port, timeout, retry_attempts, retry_rate, current_attempt + 1)

        else:
            certificate = x509.load_pem_x509_certificate(seednode_certificate.encode(),
                                                         backend=default_backend())
            return certificate

    def enact_policy(self, ursula, id, payload):
        response = requests.post('https://{}/kFrag/{}'.format(ursula.rest_interface, id.hex()), payload,
                                 verify=ursula.certificate_filepath, timeout=2)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return True, ursula.stamp.as_umbral_pubkey()

    def reencrypt(self, work_order):
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order)
        # TODO: Check status code.
        splitter = BytestringSplitter((CapsuleFrag, VariableLengthBytestring), Signature)
        cfrags_and_signatures = splitter.repeat(ursula_rest_response.data)
        cfrags = work_order.complete(cfrags_and_signatures)
        return cfrags

    def revoke_arrangement(self, ursula, revocation):
        # TODO: Implement revocation confirmations
        response = requests.delete("https://{}/kFrag/{}".format(ursula.rest_interface,
                                                                revocation.arrangement_id.hex()),
                                   bytes(revocation),
                                   verify=ursula.certificate_filepath)
        if response.status_code == 200:
            return response
        elif response.status_code == 404:
            raise RuntimeError("KFrag doesn't exist to revoke with id {}".format(revocation.arrangement_id),
                               response.status_code)
        else:
            self.log.debug("Bad response during revocation: {}".format(response))
            raise RuntimeError("Bad response: {}".format(response.content), response.status_code)
        return response

    def get_competitive_rate(self):
        return NotImplemented

    def get_treasure_map_from_node(self, node, map_id):
        endpoint = "https://{}/treasure_map/{}".format(node.rest_interface, map_id)
        response = requests.get(endpoint, verify=node.certificate_filepath, timeout=2)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        endpoint = "https://{}/treasure_map/{}".format(node.rest_interface, map_id)
        response = requests.post(endpoint, data=map_payload, verify=node.certificate_filepath, timeout=2)
        return response

    def send_work_order_payload_to_ursula(self, work_order):
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        endpoint = 'https://{}/kFrag/{}/reencrypt'.format(work_order.ursula.rest_interface, id_as_hex)
        return requests.post(endpoint, payload, verify=work_order.ursula.certificate_filepath, timeout=2)

    def node_information(self, host, port, certificate_filepath):
        endpoint = "https://{}:{}/public_information".format(host, port)
        response = requests.get(endpoint, verify=certificate_filepath, timeout=2)
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))
        return response.content

    def get_nodes_via_rest(self,
                           url,
                           certificate_filepath,
                           announce_nodes=None,
                           nodes_i_need=None,
                           client=requests,
                           fleet_checksum=None):
        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes.
            pass

        if fleet_checksum:
            params = {'fleet': fleet_checksum}
        else:
            params = {}

        req_kwargs = {}

        if client is requests:
            req_kwargs["verify"] = certificate_filepath
            req_kwargs["timeout"] = 2
            req_kwargs["params"] = params
        else:
            req_kwargs["query_string"] = params

        if announce_nodes:
            payload = bytes().join(bytes(VariableLengthBytestring(n)) for n in announce_nodes)
            response = client.post("https://{}/node_metadata".format(url),
                                   data=payload,
                                   **req_kwargs)
        else:
            response = client.get("https://{}/node_metadata".format(url), **req_kwargs)

        return response
