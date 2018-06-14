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
        port = node.rest_port
        address = node.ip_address
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id.hex())
        response = requests.get(endpoint, verify=False)
        return response

    def push_treasure_map_to_node(self, node, map_id, map_payload):
        port = node.rest_port
        address = node.ip_address
        endpoint = "https://{}:{}/treasure_map/{}".format(address, port, map_id.hex())
        response = requests.post(endpoint, data=map_payload, verify=False)
        return response

    def send_work_order_payload_to_ursula(self, work_order):
        payload = work_order.payload()
        hrac_as_hex = work_order.kfrag_hrac.hex()
        return requests.post('https://{}/kFrag/{}/reencrypt'.format(work_order.ursula.rest_url(), hrac_as_hex),
                             payload, verify=False)

    def ursula_from_rest_interface(self, address, port):
        return requests.get("https://{}:{}/public_keys".format(address, port), verify=False)  # TODO: TLS-only.

    def get_nodes_via_rest(self, address, port, node_ids=None):
        if node_ids:
            # Include node_ids in the request; if the teacher node doesn't know about the
            # nodes matching these ids, then it will ask other nodes via the DHT or whatever.
            raise NotImplementedError
        response = requests.get("https://{}:{}/list_nodes".format(address, port), verify=False)  # TODO: TLS-only.
        return response
