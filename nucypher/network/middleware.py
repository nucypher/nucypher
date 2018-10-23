import requests

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring

from umbral.fragments import CapsuleFrag
from twisted.logger import Logger


class RestMiddleware:
    log = Logger()

    def consider_arrangement(self, arrangement):
        node = arrangement.ursula
        response = requests.post("https://{}/consider_arrangement".format(node.rest_interface),
                                 bytes(arrangement),
                                 verify=node.certificate_filepath)

        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return response

    def _get_certificate(self, hostname, port):
        bootnode_certificate = ssl.get_server_certificate(hostname, port)
        certificate = x509.load_pem_x509_certificate(bootnode_certificate.encode(),
                                                     backend=default_backend())
        # Write certificate
        filename = '{}.{}'.format(bootnode.checksum_address, Encoding.PEM.name.lower())
        certificate_filepath = os.path.join(self.known_certificates_dir, filename)
        _write_tls_certificate(certificate=certificate, full_filepath=certificate_filepath, force=True)
        self.log.info("Saved bootnode {} TLS certificate".format(bootnode.checksum_address))


    def enact_policy(self, ursula, id, payload):
        response = requests.post('https://{}/kFrag/{}'.format(ursula.rest_interface, id.hex()), payload,
                                 verify=ursula.certificate_filepath)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return True, ursula.stamp.as_umbral_pubkey()

    def reencrypt(self, work_order):
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order)
        cfrags = BytestringSplitter((CapsuleFrag, VariableLengthBytestring)).repeat(ursula_rest_response.content)
        work_order.complete(cfrags)  # TODO: We'll do verification of Ursula's signature here.  #141
        return cfrags

    def get_competitive_rate(self):
        return NotImplemented

    def get_treasure_map_from_node(self, node, map_id):
        endpoint = "https://{}/treasure_map/{}".format(node.rest_interface, map_id)
        response = requests.get(endpoint, verify=node.certificate_filepath)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        endpoint = "https://{}/treasure_map/{}".format(node.rest_interface, map_id)
        response = requests.post(endpoint, data=map_payload, verify=node.certificate_filepath)
        return response

    def send_work_order_payload_to_ursula(self, work_order):
        payload = work_order.static_payload()
        id_as_hex = work_order.arrangement_id.hex()
        endpoint = 'https://{}/kFrag/{}/reencrypt'.format(work_order.ursula.rest_interface, id_as_hex)
        return requests.post(endpoint, payload, verify=work_order.ursula.certificate_filepath)

    def node_information(self, host, port, certificate_filepath):
        endpoint = "https://{}:{}/public_information".format(host, port)
        return requests.get(endpoint, verify=certificate_filepath)

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
                                     data=payload)
        else:
            response = requests.get("https://{}/node_metadata".format(url),
                                    verify=certificate_filepath)
        return response
