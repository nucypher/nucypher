"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

"""
Node Discovery happens in phases.  The first step is for a network actor to learn about the mere existence of a Node.
This is a straightforward step which we currently do with our own logic, but which may someday be replaced by something
like libp2p, depending on the course of development of those sorts of tools.

After this, our "Learning Loop" does four other things in sequence which are not part of the offering of node discovery tooling alone:

* Instantiation of an actual Node object (currently, an Ursula object) from node metadata.
* Validation of the node's metadata (non-interactive; shows that the Node's public material is indeed signed by the wallet holder of its Staker).
* Verification of the Node itself (interactive; shows that the REST server operating at the Node's interface matches the node's metadata).
* Verification of the Stake (reads the blockchain; shows that the Node is sponsored by a Staker with sufficient Stake to support a Policy).

These tests show that each phase of this process is done correctly, and in some cases, with attention to specific
performance bottlenecks.
"""

def test_alice_can_learn_about_a_whole_bunch_of_ursulas(ursula_federated_test_config):
    # First, we need to do some optimizing of this test in order
    # to be able to create a whole bunch of Ursulas without it freezing.
    # BEGIN CRAZY MONKEY PATCHING BLOCK
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

    def do_not_create_cert(*args, **kwargs):
        return NotACert(), NotAPrivateKey()

    def simple_remember(ursula, node, *args, **kwargs):
        address = node.checksum_address
        ursula.known_nodes[address] = node

    class NotARestApp:
        testing = True


    with GlobalLoggerSettings.pause_all_logging_while():
        with patch("nucypher.config.storages.ForgetfulNodeStorage.store_node_certificate",
                   new=lambda *args, **kwargs: "do not store cert."):
            with patch("nucypher.characters.lawful.make_rest_app",
                       new=lambda *args, **kwargs: (NotARestApp(), "this is not a datastore")):
                with patch("nucypher.characters.lawful.load_pem_x509_certificate",
                           new=lambda *args, **kwargs: NotACert()):
                    with patch("nucypher.keystore.keypairs.generate_self_signed_certificate", new=do_not_create_cert):
                        with patch("nucypher.keystore.keypairs.Keypair._private_key_source",
                                   new=lambda *args, **kwargs: NotAPrivateKey()):
                            with patch("nucypher.characters.lawful.Ursula.remember_node", new=simple_remember):
                                _ursulas = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                                                  quantity=5000, know_each_other=False)
    # END FIRST CRAZY MONKEY PATCHING BLOCK
                                all_ursulas = {u.checksum_address: u for u in _ursulas}
                                for ursula in _ursulas:
                                    ursula.known_nodes._nodes = all_ursulas
                                    ursula.known_nodes.checksum = b"This is a fleet state checksum..".hex()
    config = AliceConfiguration(dev_mode=True,
                                network_middleware=MockRestMiddlewareForLargeFleetTests(),
                                known_nodes=_ursulas,
                                federated_only=True,
                                abort_on_learning_error=True,
                                save_metadata=False,
                                reload_metadata=False)

    class VerificationTracker:
        node_verifications = 0
        metadata_verifications = 0

        @classmethod
        def fake_verify_node(cls, *args, **kwargs):
            cls.node_verifications += 1

        @classmethod
        def fake_verify_metadata(cls, *args, **kwargs):
            cls.metadata_verifications += 1

    with patch("nucypher.config.storages.ForgetfulNodeStorage.store_node_certificate",
               new=lambda *args, **kwargs: "do not store cert."):
        with patch("nucypher.characters.lawful.Ursula.verify_node", new=VerificationTracker.fake_verify_node):
            with patch("nucypher.network.nodes.FleetStateTracker.record_fleet_state", new=lambda *args, **kwargs: None):
                alice = config.produce(known_nodes=list(_ursulas)[:1],
                                                            )
    # We started with one known_node and verified it.
    # TODO: Consider changing this - #1449
    assert VerificationTracker.node_verifications == 1

    with patch("nucypher.config.storages.ForgetfulNodeStorage.store_node_certificate",
               new=lambda *args, **kwargs: "do not store cert."):
        with patch("nucypher.characters.lawful.Ursula.verify_node", new=VerificationTracker.fake_verify_node):
            with patch("nucypher.network.nodes.Teacher.validate_metadata", new=VerificationTracker.fake_verify_metadata):
                with patch('nucypher.characters.lawful.Alice.verify_from', new=lambda *args, **kwargs: None):
                    with patch('umbral.keys.UmbralPublicKey.from_bytes', NotAPublicKey.from_bytes):
                        with patch('nucypher.characters.lawful.load_pem_x509_certificate', new=lambda *args, **kwargs: NotACert()):
                            with patch('nucypher.crypto.signing.SignatureStamp.__call__', new=NotAPrivateKey.stamp):
                                with patch('umbral.signing.Signature.__bytes__', new=NotAPrivateKey.signature_bytes):
                                    started = time.time()
                                    alice.block_until_number_of_known_nodes_is(8, learn_on_this_thread=True, timeout=60)
                                    ended = time.time()
                                    elapsed = ended - started

    assert VerificationTracker.node_verifications == 1 # We have only verified the first Ursula.
    assert sum(isinstance(u, Ursula) for u in alice.known_nodes) < 20  # We haven't instantiated many Ursulas.
    assert elapsed < 8  # 8 seconds is still a little long to discover 8 out of 5000 nodes, but before starting the optimization that went with this test, this operation took about 18 minutes on jMyles' laptop.

