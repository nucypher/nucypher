import requests

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from umbral.fragments import CapsuleFrag


class RestMiddleware:

    def consider_arrangement(self, arrangement):
        node = arrangement.ursula
        port = node.rest_interface.port
        address = node.rest_interface.host
        response = requests.post("https://{}:{}/consider_arrangement".format(address, port), bytes(arrangement), verify=False)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return response

    def enact_policy(self, ursula, id, payload):
        port = ursula.rest_interface.port
        address = ursula.rest_interface.host
        response = requests.post('https://{}:{}/kFrag/{}'.format(address, port, id.hex()), payload, verify=False)
        if not response.status_code == 200:
            raise RuntimeError("Bad response: {}".format(response.content))
        return True, ursula.stamp.as_umbral_pubkey()

    def reencrypt(self, work_order):
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order)
        cfrags = BytestringSplitter((CapsuleFrag, VariableLengthBytestring)).repeat(ursula_rest_response.content)
        work_order.complete(cfrags)  # TODO: We'll do verification of Ursula's signature here.  #141
        return cfrags

    def revoke_arrangement(self, ursula, arrangement_id):
        port = ursula.rest_port
        address = ursula.rest_port
        response = requests.post("https://{}:{}/kFrag/revoke".format(address, port), arrangement_id)
        if not response.status_code == 200:
            if response.status_code == 404:
                raise RuntimeError("KFrag doesn't exist to revoke with id {}".format(arrangement_id), response.status_code)
            raise RuntimeError("Bad response: {}".format(response.content), response.status_code)
        return response

    def get_competitive_rate(self):
        return NotImplemented

    def get_treasure_map_from_node(self, node, map_id):
        port = node.rest_interface.port
        address = node.rest_interface.host
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id)
        response = requests.get(endpoint, verify=False)
        return response

    def put_treasure_map_on_node(self, node, map_id, map_payload):
        port = node.rest_interface.port
        address = node.rest_interface.host
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id)
        response = requests.post(endpoint, data=map_payload, verify=False)
        return response

    def send_work_order_payload_to_ursula(self, work_order):
        payload = work_order.payload()
        id_as_hex = work_order.arrangement_id.hex()
        return requests.post('https://{}/kFrag/{}/reencrypt'.format(work_order.ursula.rest_url(), id_as_hex),
                             payload, verify=False)

    def node_information(self, host, port):
        return requests.get("https://{}:{}/public_information".format(host, port), verify=False)  # TODO: TLS-only.

    def get_nodes_via_rest(self, address, port, announce_nodes=None, nodes_i_need=None):
        if nodes_i_need:
            # TODO: This needs to actually do something.
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes via the DHT or whatever.
            pass
        if announce_nodes:
            response = requests.post("https://{}:{}/node_metadata".format(address, port),
                                     verify=False,
                                     data=bytes().join(bytes(n) for n in announce_nodes))  # TODO: TLS-only.
        else:
            response = requests.get("https://{}:{}/node_metadata".format(address, port),
                                    verify=False)  # TODO: TLS-only.
        return response
