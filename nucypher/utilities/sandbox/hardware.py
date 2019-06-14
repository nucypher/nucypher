from abc import ABC


class MockTrustedDevice(ABC):
    pass


class MockTrezor(MockTrustedDevice):

    def sign_tx(self,
                client,
                n,
                nonce,
                gas_price,
                gas_limit,
                to,
                value,
                data=None,
                chain_id=None,
                tx_type=None):

        class Response:
            v = None
            r = None
            s = None

        response = Response()
        return response.v, response.r, response.s
