from unittest.mock import patch

from umbral.config import default_params
from umbral.signing import Signature

mock_cert_storage = patch("nucypher.config.storages.ForgetfulNodeStorage.store_node_certificate",
                          new=lambda *args, **kwargs: "do not store cert.")
mock_message_verification = patch('nucypher.characters.lawful.Alice.verify_from', new=lambda *args, **kwargs: None)

mock_record_fleet_state = patch("nucypher.network.nodes.FleetStateTracker.record_fleet_state",
                                new=lambda *args, **kwargs: None)


class NotAPublicKey:
    _serial = 10000

    @classmethod
    def tick(cls):
        cls._serial += 1

    def __init__(self, serial=None):
        if serial is None:
            self.tick()
            self.serial = str(self._serial).encode()
        else:
            self.serial = serial

    def __bytes__(self):
        return b"not a compressed public key:" + self.serial

    @classmethod
    def from_bytes(cls, some_bytes):
        return cls(serial=some_bytes[-5:])

    def to_bytes(self, *args, **kwargs):
        return b"this is not a public key... but it is 64 bytes.. so, ya know" + self.serial


class NotAPrivateKey:
    params = default_params()

    fake_signature = Signature.from_bytes(
        b'@\xbfS&\x97\xb3\x9e\x9e\xd3\\j\x9f\x0e\x8fY\x0c\xbeS\x08d\x0b%s\xf6\x17\xe2\xb6\xcd\x95u\xaapON\xd9E\xb3\x10M\xe1\xf4u\x0bL\x99q\xd6\r\x8e_\xe5I\x1e\xe5\xa2\xcf\xe5\x8be_\x077Gz'
    )

    def public_key(self):
        return NotAPublicKey()

    def get_pubkey(self, *args, **kwargs):
        return self.public_key()

    def to_cryptography_privkey(self, *args, **kwargs):
        return self

    def sign(self, *args, **kwargs):
        return b'0D\x02 @\xbfS&\x97\xb3\x9e\x9e\xd3\\j\x9f\x0e\x8fY\x0c\xbeS\x08d\x0b%s\xf6\x17\xe2\xb6\xcd\x95u\xaap\x02 ON\xd9E\xb3\x10M\xe1\xf4u\x0bL\x99q\xd6\r\x8e_\xe5I\x1e\xe5\xa2\xcf\xe5\x8be_\x077Gz'

    @classmethod
    def stamp(cls, *args, **kwargs):
        return cls.fake_signature

    @classmethod
    def signature_bytes(cls, *args, **kwargs):
        return b'@\xbfS&\x97\xb3\x9e\x9e\xd3\\j\x9f\x0e\x8fY\x0c\xbeS\x08d\x0b%s\xf6\x17\xe2\xb6\xcd\x95u\xaapON\xd9E\xb3\x10M\xe1\xf4u\x0bL\x99q\xd6\r\x8e_\xe5I\x1e\xe5\xa2\xcf\xe5\x8be_\x077Gz'


class NotACert:
    class Subject:
        def get_attributes_for_oid(self, *args, **kwargs):
            class Pseudonym:
                value = "0x51347fF6eb8F1D39B83B5e9c244Dc2E1E9EB14B4"

            return Pseudonym(), "Or whatever?"

    subject = Subject()

    def public_bytes(self, does_not_matter):
        return b"this is not a cert."

    def public_key(self):
        return NotAPublicKey()


mock_cert_loading = patch("nucypher.characters.lawful.load_pem_x509_certificate",
                          new=lambda *args, **kwargs: NotACert())


def do_not_create_cert(*args, **kwargs):
    return NotACert(), NotAPrivateKey()


def simple_remember(ursula, node, *args, **kwargs):
    address = node.checksum_address
    ursula.known_nodes[address] = node


class NotARestApp:
    testing = True
    _actual_rest_apps = []
    _replaced_routes = {}

    def __init__(self, this_node, *args, **kwargs):
        self._actual_rest_app = None
        self.this_node = this_node

    @classmethod
    @contextmanager
    def replace_route(cls, route_name, new_route):
        cls._replaced_routes[route_name] = new_route
        yield
        del cls._replaced_routes[route_name]

    class _ViewFunctions:
        def __init__(self, _old_view_functions=None):
            self._view_functions_registry = _old_view_functions or {}

        def __getitem__(self, route_name):
            try:
                return NotARestApp._replaced_routes[route_name]
            except KeyError:
                return self._view_functions_registry[route_name]


    def actual_rest_app(self):
        if self._actual_rest_app is None:
            self._actual_rest_app, _keystore = make_rest_app(db_filepath="no datastore",
                          this_node=self.this_node,
                          serving_domains=(None,))
            _new_view_functions = self._ViewFunctions(self._actual_rest_app.view_functions)
            self._actual_rest_app.view_functions = _new_view_functions
            self._actual_rest_apps.append(self._actual_rest_app)  # Remember now, we're appending to the class-bound list.
        return self._actual_rest_app

    def test_client(self):
        rest_app = self.actual_rest_app()
        return rest_app.test_client()


class VerificationTracker:
    node_verifications = 0
    metadata_verifications = 0

    @classmethod
    def fake_verify_node(cls, *args, **kwargs):
        cls.node_verifications += 1

    @classmethod
    def fake_verify_metadata(cls, *args, **kwargs):
        cls.metadata_verifications += 1


mock_cert_generation = patch("nucypher.keystore.keypairs.generate_self_signed_certificate", new=do_not_create_cert)
mock_rest_app_creation = patch("nucypher.characters.lawful.make_rest_app",
                               new=lambda *args, **kwargs: (NotARestApp(), "this is not a datastore"))
mock_secret_source = patch("nucypher.keystore.keypairs.Keypair._private_key_source",
                           new=lambda *args, **kwargs: NotAPrivateKey())

mock_remember_node = patch("nucypher.characters.lawful.Ursula.remember_node", new=simple_remember)
mock_verify_node = patch("nucypher.characters.lawful.Ursula.verify_node", new=VerificationTracker.fake_verify_node)

mock_metadata_validation = patch("nucypher.network.nodes.Teacher.validate_metadata",
                                 new=VerificationTracker.fake_verify_metadata)

mock_pubkey_from_bytes = patch('umbral.keys.UmbralPublicKey.from_bytes', NotAPublicKey.from_bytes)
mock_stamp_call = patch('nucypher.crypto.signing.SignatureStamp.__call__', new=NotAPrivateKey.stamp)
mock_signature_bytes = patch('umbral.signing.Signature.__bytes__', new=NotAPrivateKey.signature_bytes)
