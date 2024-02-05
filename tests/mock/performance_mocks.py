from contextlib import contextmanager
from unittest.mock import patch

from nucypher_core.umbral import PublicKey

from nucypher.network.server import make_rest_app
from tests.mock.serials import good_serials

mock_message_verification = patch('nucypher.characters.lawful.Alice.verify_from', new=lambda *args, **kwargs: None)


def fake_keep_learning(selfish, learner=None, *args, **kwargs):
    return None


mock_keep_learning = patch('nucypher.network.nodes.Learner.keep_learning_about_nodes', new=fake_keep_learning)

mock_record_fleet_state = patch("nucypher.acumen.perception.FleetSensor.record_fleet_state",
                                new=lambda *args, **kwargs: None)

"""
Some hairy stuff ahead.  We want 5,000 Ursulas for some of these tests.  OK, so what effect does that have?  For one thing, if you generate 5k Ursulas, you end up generate some 20k keypairs (validating, signing, delegating, and TLSHosting for each of the 5k Ursulas). That causes this test to go from taking about 7s total (on jMyles' laptop) to about 2min. So that's obviously unacceptable.

Instead, we generate mock keys in serial, and then, when Alice chooses her 8 Ursulas (out of the 4000 about whom she has learned, out of the 5000 that we have made), she verifies them, and at this stage, we're no longer mocking out, which causes the bytes of the key to be cast back into a real key.

The problem is that, for any mock key string, there are going to be some bytes that aren't properly formatted to be a real key. So, I have included all of the numbers which ultimately produce bytes which can't be used as a public key.

The only other obvious way to have a test this fast is to hardcode 20k keypairs into the codebase (and even then, it will be far, far less performant than this).
"""


class NotAPublicKey:
    _serial_bytes_length = 5
    _serial = 10000

    _umbral_pubkey_from_bytes = PublicKey.from_compressed_bytes

    def _tick():
        for serial in good_serials:
            yield serial
    tick = _tick()

    def __init__(self, serial=None):
        if serial is None:
            serial_int = next(self.tick)
            self.serial = serial_int.to_bytes(self._serial_bytes_length, byteorder="big")
        else:
            self.serial = serial

    def __bytes__(self):
        return b"\x03  not a compress publickey:" + self.serial

    @classmethod
    def reset(cls):
        cls.tick = cls._tick()

    @classmethod
    def from_bytes(cls, some_bytes):
        return cls(serial=some_bytes[-5:])

    @classmethod
    def from_int(cls, serial):
        return cls(serial.to_bytes(cls._serial_bytes_length, byteorder="big"))

    def i_want_to_be_a_real_boy(self):
        return self._umbral_pubkey_from_bytes(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)


class NotAPrivateKey:

    def public_key(self):
        return NotAPublicKey()


class NotASignature:

    fake_signature_bytes = b'@\xbfS&\x97\xb3\x9e\x9e\xd3\\j\x9f\x0e\x8fY\x0c\xbeS\x08d\x0b%s\xf6\x17\xe2\xb6\xcd\x95u\xaapON\xd9E\xb3\x10M\xe1\xf4u\x0bL\x99q\xd6\r\x8e_\xe5I\x1e\xe5\xa2\xcf\xe5\x8be_\x077Gz'

    def __bytes__(self):
        return self.fake_signature_bytes


class NotASigner:

    def __init__(self, secret_key):
        self._secret_key = secret_key

    def sign(self, message):
        return NotASignature()


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


mock_cert_loading = patch("nucypher.network.nodes.load_der_x509_certificate",
                          new=lambda *args, **kwargs: NotACert())


def do_not_create_cert(*args, **kwargs):
    return NotACert(), NotAPrivateKey()


def simple_remember(ursula, node, *args, **kwargs):
    ursula.known_nodes.record_node(node)


class NotARestApp:
    testing = True
    _actual_rest_apps = []
    _replaced_routes = {}

    def __init__(self, this_node, *args, **kwargs):
        self._actual_rest_app = None
        self.this_node = this_node

    @classmethod
    def create(cls, *args, **kwargs):
        return cls(*args, **kwargs)

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
            self._actual_rest_app = make_rest_app(this_node=self.this_node)
            _new_view_functions = self._ViewFunctions(self._actual_rest_app.view_functions)
            self._actual_rest_app.view_functions = _new_view_functions
            self._actual_rest_apps.append(
                self._actual_rest_app)  # Remember now, we're appending to the class-bound list.
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


mock_cert_generation = patch("nucypher.crypto.tls.generate_self_signed_certificate", new=do_not_create_cert)
mock_rest_app_creation = patch("nucypher.characters.lawful.make_rest_app",
                               new=NotARestApp.create)

mock_remember_node = patch("nucypher.characters.lawful.Ursula.remember_node", new=simple_remember)
mock_verify_node = patch("nucypher.characters.lawful.Ursula.verify_node", new=VerificationTracker.fake_verify_node)

mock_metadata_validation = patch("nucypher.network.nodes.Teacher.validate_metadata",
                                 new=VerificationTracker.fake_verify_metadata)


@contextmanager
def mock_secret_source(*args, **kwargs):
    with patch("nucypher.crypto.keypairs.Keypair._private_key_source", new=lambda *args, **kwargs: NotAPrivateKey()):
        with patch("nucypher.crypto.keypairs.Signer", new=lambda *args, **kwargs: NotASigner(*args, **kwargs)):
            yield
    NotAPublicKey.reset()


def _determine_good_serials(start, end):
    """
    Figure out which serials are good to use in mocks because they won't result in non-viable public keys.
    """
    good_serials = []
    for i in range(start, end):
        try:
            NotAPublicKey.from_int(i).i_want_to_be_a_real_boy()
        except Exception:
            continue
        else:
            good_serials.append(i)
    return good_serials
