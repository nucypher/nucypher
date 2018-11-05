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
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from twisted.logger import Logger
from umbral.fragments import CapsuleFrag
from umbral.signing import Signature


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

    def get_certificate(self, host, port,
                         timeout=3, retry_attempts: int = 3, retry_rate: int = 2, ):

        socket.setdefaulttimeout(timeout)  # Set Socket Timeout
        current_attempt = 0
        try:
            self.log.info("Fetching seednode {}:{} TLS certificate".format(host, port))
            seednode_certificate = ssl.get_server_certificate(addr=(host, port))
        except socket.timeout:
            if current_attempt == retry_attempts:
                message = "No Response from seednode {}:{} after {} attempts"
                self.log.info(message.format(host, port, retry_attempts))
                return False
            self.log.info(
                "No Response from seednode {}. Retrying in {} seconds...".format(checksum_address, retry_rate))
            time.sleep(retry_rate)

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
        cfrags_and_signatures = BytestringSplitter((CapsuleFrag, VariableLengthBytestring), Signature).repeat(
            ursula_rest_response.content)
        cfrags = work_order.complete(
            cfrags_and_signatures)
        return cfrags

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
        return requests.get(endpoint, verify=certificate_filepath, timeout=2)

    def get_nodes_via_rest(self,
                           url,
                           certificate_filepath,
                           announce_nodes=None,
                           nodes_i_need=None):
        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes.
            pass

        if announce_nodes:
            payload = bytes().join(bytes(n) for n in announce_nodes)
            response = requests.post("https://{}/node_metadata".format(url),
                                     verify=certificate_filepath,
                                     data=payload, timeout=2)
        else:
            response = requests.get("https://{}/node_metadata".format(url),
                                    verify=certificate_filepath, timeout=2)
        return response
