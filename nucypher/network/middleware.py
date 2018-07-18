import requests

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from umbral.fragments import CapsuleFrag


class RestMiddleware:

    def consider_arrangement(self, ursula, arrangement=None):
        pass

    def reencrypt(self, work_order):
        ursula_rest_response = self.send_work_order_payload_to_ursula(work_order)
        cfrags = BytestringSplitter((CapsuleFrag, VariableLengthBytestring)).repeat(ursula_rest_response.content)
        work_order.complete(cfrags)  # TODO: We'll do verification of Ursula's signature here.  #141
        return cfrags

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
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes via the DHT or whatever.
            raise NotImplementedError
        if announce_nodes:
            response = requests.post("https://{}:{}/node_metadata".format(address, port),
                                     verify=False,
                                     data=bytes().join(bytes(n) for n in announce_nodes))  # TODO: TLS-only.
        else:
            response = requests.get("https://{}:{}/node_metadata".format(address, port),
                                    verify=False)  # TODO: TLS-only.
        return response
