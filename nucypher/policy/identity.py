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

import base64
import json
from pathlib import Path
from typing import Union, Optional, Dict, Callable

import constant_sorrow
import hashlib
import os
from bytestring_splitter import VariableLengthBytestring, BytestringKwargifier
from constant_sorrow.constants import ALICE, BOB, NO_SIGNATURE
from hexbytes.main import HexBytes
from umbral.keys import UmbralPublicKey

from nucypher.characters.base import Character
from nucypher.characters.lawful import Alice, Bob
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.policy.collections import TreasureMap


class Card:
    """"
    A simple serializable representation of a character's public materials.
    """

    _specification = dict(
        character_flag=(bytes, 8),
        verifying_key=(UmbralPublicKey, 33),
        encrypting_key=(UmbralPublicKey, 33),
        nickname=(bytes, VariableLengthBytestring),
    )

    __CARD_TYPES = {
        bytes(ALICE): Alice,
        bytes(BOB): Bob,
    }

    __ID_LENGTH = 20  # TODO: Review this size
    __MAX_NICKNAME_SIZE = 10
    __BASE_PAYLOAD_SIZE = sum(length[1] for length in _specification.values() if isinstance(length[1], int))
    __MAX_CARD_LENGTH = __BASE_PAYLOAD_SIZE + __MAX_NICKNAME_SIZE
    __FILE_EXTENSION = 'card'
    CARD_DIR = Path(DEFAULT_CONFIG_ROOT) / 'cards'
    NO_SIGNATURE.bool_value(False)

    class InvalidCard(Exception):
        """Raised when an invalid, corrupted, or otherwise unsable card is encountered"""

    class UnknownCard(Exception):
        """Raised when a card cannot be found in storage"""

    class UnsignedCard(Exception):
        """Raised when a card serialization cannot be handled due to the lack of a signature"""

    def __init__(self,
                 character_flag: Union[ALICE, BOB],
                 verifying_key: Union[UmbralPublicKey, bytes],
                 encrypting_key: Optional[Union[UmbralPublicKey, bytes]] = None,
                 card_dir: Path = CARD_DIR,
                 nickname: Optional[Union[bytes, str]] = None):

        try:
            self.__character_class = self.__CARD_TYPES[bytes(character_flag)]
        except KeyError:
            raise ValueError(f'Unsupported card type {str(character_flag)}')
        self.__character_flag = character_flag

        if isinstance(verifying_key, bytes):
            verifying_key = UmbralPublicKey.from_bytes(verifying_key)
        self.__verifying_key = verifying_key    # signing public key

        if isinstance(encrypting_key, bytes):
            encrypting_key = UmbralPublicKey.from_bytes(encrypting_key)
        self.__encrypting_key = encrypting_key  # public key

        if isinstance(nickname, str):
            nickname = nickname.encode()
        self.__nickname = nickname

        self.__validate()
        self.card_dir = card_dir

    def __repr__(self) -> str:
        name = self.nickname or f'{self.__character_class.__name__}'
        short_key = bytes(self.__verifying_key).hex()[:6]
        r = f'{self.__class__.__name__}({name}:{short_key}:{self.id.hex()[:6]})'
        return r

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError(f'Cannot compare {self.__class__.__name__} and {other}')
        return self.id == other.id

    def __validate(self) -> bool:
        if self.__nickname and (len(self.__nickname) > self.__MAX_NICKNAME_SIZE):
            raise self.InvalidCard(f'Nickname exceeds maximum length')
        return True

    @classmethod
    def __hash(cls, payload: bytes) -> HexBytes:
        blake = hashlib.blake2b()
        blake.update(payload)
        digest = blake.digest().hex()
        truncated_digest = digest[:cls.__ID_LENGTH]
        return HexBytes(truncated_digest)

    @property
    def character(self):
        return self.__CARD_TYPES[self.__character_flag]

    #
    # Serializers
    #

    def __bytes__(self) -> bytes:
        self.__validate()
        payload = self.__payload
        if self.nickname:
            payload += VariableLengthBytestring(self.__nickname)
        return payload

    def __hex__(self) -> str:
        return self.to_hex()

    @property
    def __payload(self) -> bytes:
        elements = (
            self.__character_flag,
            self.__verifying_key,
            self.__encrypting_key,
        )
        payload = b''.join(bytes(e) for e in elements)
        return payload

    @classmethod
    def from_bytes(cls, card_bytes: bytes) -> 'Card':
        if len(card_bytes) > cls.__MAX_CARD_LENGTH:
            raise cls.InvalidCard(f'Card exceeds maximum size. Verify the card filepath and contents.')
        return BytestringKwargifier(cls, **cls._specification)(card_bytes)

    @classmethod
    def from_hex(cls, hexdata: str):
        return cls.from_bytes(bytes.fromhex(hexdata))

    def to_hex(self) -> str:
        return bytes(self).hex()

    @classmethod
    def from_base64(cls, b64data: str):
        return cls.from_bytes(base64.urlsafe_b64decode(b64data))

    def to_base64(self) -> str:
        return base64.urlsafe_b64encode(bytes(self)).decode()

    def to_qr_code(self):
        import qrcode
        from qrcode.main import QRCode
        qr = QRCode(
            version=1,
            box_size=1,
            border=4,  # min spec is 4
            error_correction=qrcode.constants.ERROR_CORRECT_L,
        )
        qr.add_data(bytes(self))
        qr.print_ascii()

    @classmethod
    def from_dict(cls, card: Dict):
        instance = cls(nickname=card.get('nickname'),
                       verifying_key=card['verifying_key'],
                       encrypting_key=card['encrypting_key'],
                       character_flag=card['character'])
        return instance

    def to_dict(self) -> Dict:
        payload = dict(
            nickname=self.__nickname,
            verifying_key=self.verifying_key,
            encrypting_key=self.encrypting_key,
            character=self.__character_flag
        )
        return payload

    def to_json(self, as_string: bool = True) -> Union[dict, str]:
        payload = dict(
            nickname=self.__nickname.decode(),
            verifying_key=bytes(self.verifying_key).hex(),
            encrypting_key=bytes(self.encrypting_key).hex(),
            character=bytes(self.__character_flag).hex()
        )
        if as_string:
            payload = json.dumps(payload)
        return payload

    @classmethod
    def from_character(cls, character: Character, nickname: Optional[str] = None) -> 'Card':
        flag = getattr(constant_sorrow.constants, character.__class__.__name__.upper())
        instance = cls(verifying_key=character.public_keys(power_up_class=SigningPower),
                       encrypting_key=character.public_keys(power_up_class=DecryptingPower),
                       character_flag=flag,
                       nickname=nickname)
        return instance

    #
    # Card API
    #


    @property
    def verifying_key(self) -> UmbralPublicKey:
        return self.__verifying_key

    @property
    def encrypting_key(self) -> UmbralPublicKey:
        return self.__encrypting_key

    @property
    def id(self) -> HexBytes:
        return self.__hash(self.__payload)

    @property
    def nickname(self) -> str:
        if self.__nickname:
            return self.__nickname.decode()

    def set_nickname(self, nickname: str) -> None:
        if len(nickname.encode()) > self.__MAX_NICKNAME_SIZE:
            raise ValueError(f'New nickname exceeds maximum size ({self.__MAX_NICKNAME_SIZE} bytes)')
        self.__nickname = nickname.encode()

    @nickname.setter
    def nickname(self, nickname: str) -> None:
        self.set_nickname(nickname)

    #
    # Card Storage API
    #

    @property
    def is_saved(self) -> bool:
        filename = f'{self.id.hex()}.{self.__FILE_EXTENSION}'
        filepath = self.card_dir / filename
        exists = filepath.exists()
        return exists

    def save(self, encoder: Callable = base64.b64encode, overwrite: bool = False) -> Path:
        if not self.card_dir.exists():
            os.mkdir(str(self.card_dir))
        filename = f'{self.nickname+":" if self.__nickname else str()}{self.id.hex()}.{self.__FILE_EXTENSION}'
        filepath = self.card_dir / filename
        if filepath.exists() and not overwrite:
            raise FileExistsError('Card exists. Pass overwrite=True to allow this operation.')
        with open(str(filepath), 'wb') as file:
            file.write(encoder(bytes(self)))
        return Path(filepath)

    @classmethod
    def load(cls,
             checksum: str = None,
             nickname: str = None,
             card_dir: Path = CARD_DIR,
             decoder: Callable = base64.b64decode
             ) -> 'Card':
        if nickname:
            for filename in os.listdir(Card.CARD_DIR):
                if nickname.casefold() in filename.casefold():
                    break
            else:
                raise ValueError(f'Unknown card nickname "{nickname}"')
            name, _extension = filename.split('.')  # TODO: glob or regex?
            parsed_nickname, parsed_checksum = name.split(':')
            if parsed_nickname != nickname:
                raise ValueError('Nickname matches another')
        elif checksum:
            filename = f'{checksum}.{cls.__FILE_EXTENSION}'
        else:
            raise ValueError  # TODO
        filepath = card_dir / filename
        try:
            with open(str(filepath), 'rb') as file:
                card_bytes = decoder(file.read())
        except FileNotFoundError:
            raise cls.UnknownCard
        instance = cls.from_bytes(card_bytes)
        return instance


class PolicyCredential:
    """
    A portable structure that contains information necessary for Alice or Bob
    to utilize the policy on the network that the credential describes.
    """

    def __init__(self, alice_verifying_key, label, expiration, policy_pubkey,
                 treasure_map=None):
        self.alice_verifying_key = alice_verifying_key
        self.label = label
        self.expiration = expiration
        self.policy_pubkey = policy_pubkey
        self.treasure_map = treasure_map

    def to_json(self):
        """
        Serializes the PolicyCredential to JSON.
        """
        cred_dict = {
            'alice_verifying_key': bytes(self.alice_verifying_key).hex(),
            'label': self.label.hex(),
            'expiration': self.expiration.iso8601(),
            'policy_pubkey': bytes(self.policy_pubkey).hex()
        }

        if self.treasure_map is not None:
            cred_dict['treasure_map'] = bytes(self.treasure_map).hex()

        return json.dumps(cred_dict)

    @classmethod
    def from_json(cls, data: str):
        """
        Deserializes the PolicyCredential from JSON.
        """
        cred_json = json.loads(data)

        alice_verifying_key = UmbralPublicKey.from_bytes(
                                    cred_json['alice_verifying_key'],
                                    decoder=bytes().fromhex)
        label = bytes().fromhex(cred_json['label'])
        expiration = maya.MayaDT.from_iso8601(cred_json['expiration'])
        policy_pubkey = UmbralPublicKey.from_bytes(
                            cred_json['policy_pubkey'],
                            decoder=bytes().fromhex)
        treasure_map = None

        if 'treasure_map' in cred_json:
            treasure_map = TreasureMap.from_bytes(
                                bytes().fromhex(cred_json['treasure_map']))

        return cls(alice_verifying_key, label, expiration, policy_pubkey,
                   treasure_map)

    def __eq__(self, other):
        return ((self.alice_verifying_key == other.alice_verifying_key) and
                (self.label == other.label) and
                (self.expiration == other.expiration) and
                (self.policy_pubkey == other.policy_pubkey))
