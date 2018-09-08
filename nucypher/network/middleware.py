import requests

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring

from nucypher.config.constants import DEFAULT_TLS_CERTIFICATE_FILEPATH
from nucypher.crypto.api import load_tls_certificate
from umbral.fragments import CapsuleFrag


class RestMiddleware:

    def consider_arrangement(self, arrangement, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        node = arrangement.ursula
        port = node.rest_interface.port
        address = node.rest_interface.host
        response = requests.post("https://{}:{}/consider_arrangement".format(address, port), bytes(arrangement), verify=certificate)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return response

    def enact_policy(self, ursula, id, payload, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        port = ursula.rest_interface.port
        address = ursula.rest_interface.host
        response = requests.post('https://{}:{}/kFrag/{}'.format(address, port, id.hex()), payload, verify=certificate)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return True, ursula.stamp.as_umbral_pubkey()

    def reencrypt(self, work_order, certificate_path):
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order, certificate_path=certificate_path)
        cfrags = BytestringSplitter((CapsuleFrag, VariableLengthBytestring)).repeat(ursula_rest_response.content)
        work_order.complete(cfrags)  # TODO: We'll do verification of Ursula's signature here.  #141
        return cfrags

    def get_competitive_rate(self):
        return NotImplemented

    def get_treasure_map_from_node(self, node, map_id, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        port = node.rest_interface.port
        address = node.rest_interface.host
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id)
        response = requests.get(endpoint, verify=certificate)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        port = node.rest_interface.port
        address = node.rest_interface.host
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id)
        response = requests.post(endpoint, data=map_payload, verify=certificate)
        return response

    def send_work_order_payload_to_ursula(self, work_order, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        endpoint = 'https://{}/kFrag/{}/reencrypt'.format(work_order.ursula.rest_url(), id_as_hex)
        return requests.post(endpoint, payload, verify=certificate)

    def node_information(self, host, port, certificate_path):
        certificate = load_tls_certificate(filepath=certificate_path)
        endpoint = "https://{}:{}/public_information".format(host, port)
        return requests.get(endpoint, verify=certificate)

    def get_nodes_via_rest(self,
                           url,
                           certificate_path=None,
                           announce_nodes=None,
                           nodes_i_need=None):
        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes via the DHT or whatever.
            pass

        certificate = load_tls_certificate(filepath=certificate_path)

        if announce_nodes:
            payload = bytes().join(bytes(n) for n in announce_nodes)
            response = requests.post("https://{}/node_metadata".format(url),
                                     verify=certificate,
                                     data=payload)
        else:
            response = requests.get("https://{}node_metadata".format(url),
                                    verify=certificate)
        return response
