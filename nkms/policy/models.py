import asyncio
import binascii

import maya
import msgpack
from npre.constants import UNKNOWN_KFRAG

from nkms.characters import Alice, Bob, Ursula
from nkms.crypto.api import keccak_digest
from nkms.crypto.constants import NOT_SIGNED, KECCAK_DIGEST_LENGTH, \
    PUBLIC_KEY_LENGTH
from nkms.crypto.powers import SigningPower
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from umbral.keys import UmbralPublicKey


class Contract(object):
    """
    A Policy must be implemented by contract with n Ursulas.  This class tracks the status of that implementation.
    """
    _EXPECTED_LENGTH = 124

    def __init__(self, alice, hrac, expiration, deposit=None, ursula=None,
                 kfrag=UNKNOWN_KFRAG, alices_signature=None):
        """
        :param deposit: Funds which will pay for the timeframe  of this Contract (not the actual re-encryptions);
            a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Contract to end.

        Other params are hopefully self-evident.
        """
        self.expiration = expiration
        self.deposit = deposit
        self.hrac = hrac
        self.alice = alice

        """
        These will normally not be set if Alice is drawing up this contract - she hasn't assigned a kfrag yet
        (because she doesn't know if this Contract will be accepted).  She doesn't have an Ursula, for the same reason.
        """
        self.kfrag = kfrag
        self.ursula = ursula

    def __bytes__(self):
        return bytes(self.alice.seal) + bytes(
            self.hrac) + self.expiration.isoformat().encode() + bytes(
            self.deposit)

    @classmethod
    def from_bytes(cls, contract_as_bytes):
        contract_splitter = BytestringSplitter(
            (UmbralPublicKey, PUBLIC_KEY_LENGTH), (bytes, KECCAK_DIGEST_LENGTH),
            (bytes, 26))
        alice_pubkey_sig, hrac, expiration_bytes, deposit_bytes = contract_splitter(
            contract_as_bytes, return_remainder=True)
        expiration = maya.parse(expiration_bytes.decode())
        alice = Alice.from_public_keys((SigningPower, alice_pubkey_sig))
        return cls(alice=alice, hrac=hrac, expiration=expiration)

    def activate(self, kfrag, ursula, negotiation_result):
        self.kfrag = kfrag
        self.ursula = ursula
        self.negotiation_result = negotiation_result

    def encrypt_payload_for_ursula(self):
        """
        Craft an offer to send to Ursula.
        """
        # We don't need the signature separately.
        return self.alice.encrypt_for(self.ursula, self.payload())[0]

    def payload(self):
        # TODO: Ship the expiration again?  Or some other way of alerting Ursula to recall her previous dialogue regarding this Contract.  Update: We'll probably have her store the Contract by hrac.  See #127.
        return bytes(self.kfrag)


class ContractResponse(object):
    pass


class Policy(object):
    """
        An edict by Alice, contracted with n Ursulas, to perform re-encryption for a specific Bob
    for a specific path.

    Once Alice is ready to enact a Policy, she generates KFrags, which become part of the Policy.

    Each Ursula is offered a Contract (see above) for a given Policy by Alice.

    Once Alice has secured agreement with n Ursulas to enact a Policy, she sends each a KFrag,
    and generates a TreasureMap for the Policy, recording which Ursulas got a KFrag.
    """

    def __init__(self, alice, bob=None, kfrags=(UNKNOWN_KFRAG,), uri=None,
                 alices_signature=NOT_SIGNED):
        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param pfrag: The input ciphertext which Bob will give to Ursula to re-encrypt.
        :param uri: The identity of the resource to which Bob is granted access.
        """
        self.alice = alice
        self.bob = bob
        self.kfrags = kfrags
        self.uri = uri
        self.treasure_map = TreasureMap()
        self._accepted_contracts = {}

        self.alices_signature = alices_signature

    class MoreContractsThanKFrags(TypeError):
        """
        Raised when a Policy has been used to generate Contracts with Ursulas in sufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self):
        return len(self.kfrags)

    @property
    def ursula(self):
        if not self._ursula:
            raise Ursula.NotFound
        else:
            return self._ursula

    @ursula.setter
    def ursula(self, ursula_object):
        self.alice.learn_about_actor(ursula_object)
        self._ursula = ursula_object

    @staticmethod
    def from_alice(kfrags,
                   alice,
                   bob,
                   uri,
                   ):
        # TODO: What happened to Alice's signature - don't we include it here?
        policy = Policy(alice, bob, kfrags, uri)

        return policy

    def hrac(self):
        """
        A convenience method for generating an hrac for this instance.
        """
        return self.hrac_for(self.alice, self.bob, self.uri)

    @staticmethod
    def hrac_for(alice, bob, uri):
        """
        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return Policy.hash(bytes(alice.seal) + bytes(bob.seal) + uri)

    @staticmethod
    def hash(message):
        return keccak_digest(message)

    def treasure_map_dht_key(self):
        """
        We need a key that Bob can glean from knowledge he already has *and* which Ursula can verify came from us.
        Ursula will refuse to propagate this key if it she can't prove that our public key, which is included in it,
        was used to sign the payload.

        Our public key (which everybody knows) and the hrac above.
        """
        return self.hash(bytes(self.alice.seal) + self.hrac())

    def publish_treasure_map(self):
        encrypted_treasure_map, signature_for_bob = self.alice.encrypt_for(
            self.bob,
            self.treasure_map.packed_payload())
        signature_for_ursula = self.alice.seal(self.hrac())

        # In order to know this is safe to propagate, Ursula needs to see a signature, our public key,
        # and, reasons explained in treasure_map_dht_key above, the uri_hash.
        dht_value = signature_for_ursula + self.alice.seal + self.hrac() + msgpack.dumps(
            encrypted_treasure_map)  # TODO: Ideally, this is a Ciphertext object instead of msgpack (see #112)
        dht_key = self.treasure_map_dht_key()

        setter = self.alice.server.set(dht_key, b"trmap" + dht_value)
        event_loop = asyncio.get_event_loop()
        event_loop.run_until_complete(setter)
        return encrypted_treasure_map, dht_value, signature_for_bob, signature_for_ursula

    def enact(self, networky_stuff):
        for contract in self._accepted_contracts.values():
            policy_payload = contract.encrypt_payload_for_ursula()
            full_payload = self.alice.seal + msgpack.dumps(policy_payload)
            response = networky_stuff.enact_policy(contract.ursula,
                                                   self.hrac(),
                                                   full_payload)  # TODO: Parse response for confirmation.

            # Assuming response is what we hope for
            self.treasure_map.add_ursula(contract.ursula)

    def draw_up_contract(self, deposit, expiration):
        return Contract(self.alice, self.hrac(), expiration=expiration,
                        deposit=deposit)

    def find_ursulas(self, networky_stuff, deposit, expiration,
                     num_ursulas=None):
        # TODO: This is a number mismatch - we need not one contract, but n contracts.
        """
        :param networky_stuff: A compliant interface (maybe a Client instance) to be used to engage the DHT swarm.
        """
        if num_ursulas is None:
            num_ursulas = self.n

        found_ursulas = []
        while len(found_ursulas) < num_ursulas:
            contract = self.draw_up_contract(deposit, expiration)
            try:
                ursula, result = networky_stuff.find_ursula(contract)
                found_ursulas.append((ursula, contract, result))
            except networky_stuff.NotEnoughQualifiedUrsulas:
                pass  # TODO: Tell Alice to either wait or lower the value of num_ursulas.
        return found_ursulas

    def assign_kfrag_to_contract(self, contract):
        for kfrag in self.kfrags:
            if not kfrag in self._accepted_contracts:
                contract.kfrag = kfrag
                self._accepted_contracts[kfrag] = contract
                return kfrag
        if not contract.kfrag:
            raise self.MoreContractsThanKFrags  # TODO: Perhaps in a future version, we consider allowing Alice to assign *the same* KFrag to multiple Ursulas?

    def match_kfrags_to_found_ursulas(self, found_ursulas):
        for ursula, contract, result in found_ursulas:
            if result.was_accepted:  # TODO: Here, we need to assess the result and see if we're actually good to go.
                kfrag = self.assign_kfrag_to_contract(contract)
                contract.activate(kfrag, ursula, result)
                # TODO: What if there weren't enough Contracts approved to distribute n kfrags?  We need to raise NotEnoughQualifiedUrsulas.


class TreasureMap(object):
    def __init__(self, ursula_interface_ids=None):
        self.ids = ursula_interface_ids or []

    def packed_payload(self):
        return msgpack.dumps(self.ids)

    def add_ursula(self, ursula):
        self.ids.append(ursula.interface_dht_key())

    def __eq__(self, other):
        return self.ids == other.ids

    def __iter__(self):
        return iter(self.ids)

    def __len__(self):
        return len(self.ids)


class WorkOrder(object):
    def __init__(self, bob, kfrag_hrac, pfrags, receipt_bytes,
                 receipt_signature, ursula_id=None):
        self.bob = bob
        self.kfrag_hrac = kfrag_hrac
        self.pfrags = pfrags
        self.receipt_bytes = receipt_bytes
        self.receipt_signature = receipt_signature
        self.ursula_id = ursula_id  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.

    def __repr__(self):
        return "WorkOrder (pfrags: {}) {} for {}".format(
            [binascii.hexlify(bytes(p))[:6] for p in self.pfrags],
            binascii.hexlify(self.receipt_bytes)[:6],
            binascii.hexlify(self.ursula_id)[:6])

    def __eq__(self, other):
        return (self.receipt_bytes, self.receipt_signature) == (
        other.receipt_bytes, other.receipt_signature)

    def __len__(self):
        return len(self.pfrags)

    @classmethod
    def constructed_by_bob(cls, kfrag_hrac, pfrags, ursula_dht_key, bob):
        receipt_bytes = b"wo:" + ursula_dht_key  # TODO: represent the pfrags as bytes and hash them as part of the receipt, ie  + keccak_digest(b"".join(pfrags))  - See #137
        receipt_signature = bob.seal(receipt_bytes)
        return cls(bob, kfrag_hrac, pfrags, receipt_bytes, receipt_signature, ursula_dht_key)

    @classmethod
    def from_rest_payload(cls, kfrag_hrac, rest_payload):
        payload_splitter = BytestringSplitter(Signature, PublicKey)
        signature, bob_pubkey_sig, (receipt_bytes, packed_pfrags) = payload_splitter(rest_payload,
                                                                                     msgpack_remainder=True)
        pfrags = [PFrag(p) for p in msgpack.loads(packed_pfrags)]
        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise ValueError("This doesn't appear to be from Bob.")
        bob = Bob.from_public_keys((SigningPower, bob_pubkey_sig))
        return cls(bob, kfrag_hrac, pfrags, receipt_bytes, signature)

    def payload(self):
        pfrags_as_bytes = [bytes(p) for p in self.pfrags]
        packed_receipt_and_pfrags = msgpack.dumps((self.receipt_bytes, msgpack.dumps(pfrags_as_bytes)))
        return bytes(self.receipt_signature) + self.bob.seal + packed_receipt_and_pfrags

    def complete(self, cfrags):
        # TODO: Verify that this is in fact complete - right of CFrags and properly signed.
        # TODO: Mark it complete with datetime.
        self
