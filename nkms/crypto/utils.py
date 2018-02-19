from contextlib import suppress
from typing import Any

import msgpack
from umbral.keys import UmbralPublicKey

from nkms.crypto.api import keccak_digest


class BytestringSplitter(object):

    def __init__(self, *message_types):
        """
        :param message_types:  A collection of types of messages to parse.
        """
        self.message_types = []
        if not message_types:
            raise ValueError(
                "Can't make a BytestringSplitter unless you specify what to split!")

        for counter, message_type in enumerate(message_types):
        # message_types can be tuples (with length and kwargs) or just classes.
            if isinstance(message_types, tuple):
                # Here, it's a tuple - these are our message types.
                self.message_types.extend(message_types)

                # We're ready to break out of the loop, because we
                # already have our message type.

                # However, before we do, let's address a possible mis-step
                # by the user and offer a better error message.
                with suppress(IndexError):
                    if isinstance(message_types[counter + 1], int):
                        raise TypeError("You can't specify the length of the message as a direct argument to the constructor.  Instead, pass it as the second argument in a tuple (with the class as the first argument)")
                # OK, cool - break.
                break
            else:
                # OK, it's an object.  If it's a tuple, we can just add it.
                if isinstance(message_type, tuple):
                    self.message_types.append(message_type)
                else:
                    # Otherwise, it's a class - turn it into a tuple for
                    # compatibility with get_message_meta later.
                    message_type_tuple = message_type,
                    self.message_types.append(message_type_tuple)



    def __call__(self, splittable, return_remainder=False, msgpack_remainder=False):
        if not any((return_remainder, msgpack_remainder)) and len(self) != len(splittable):
            raise ValueError(
                """"Wrong number of bytes to constitute message types {} - 
                need {}, got {} \n Did you mean to return the remainder?""".format(
                    self.message_types, len(self), len(splittable)))
        if len(self) > len(splittable):
            raise ValueError(
                """Not enough bytes to constitute
                message types {} - need {}, got {}""".format(self.message_types,
                                                           len(self),
                                                           len(splittable)))
        cursor = 0
        message_objects = []

        for message_type in self.message_types:
            message_class, message_length, kwargs = self.get_message_meta(message_type)
            expected_end_of_object_bytes = cursor + message_length
            bytes_for_this_object = splittable[cursor:expected_end_of_object_bytes]
            try:
                message = message_class.from_bytes(bytes_for_this_object, **kwargs)
            except AttributeError:
                message = message_class(bytes_for_this_object, **kwargs)

            message_objects.append(message)
            cursor = expected_end_of_object_bytes

        remainder = splittable[cursor:]

        if msgpack_remainder:
            message_objects.append(msgpack.loads(remainder))
        elif return_remainder:
            message_objects.append(remainder)

        return message_objects

    def __len__(self):
        return sum(self.get_message_meta(m)[1] for m in self.message_types)


    @staticmethod
    def get_message_meta(message_type):
        try:
            message_class = message_type[0]
        except TypeError:
            message_class = message_type

        try:
            # If a message length has been passed manually, it will be the second item.
            message_length = message_type[1]
        except TypeError:
            # If not, we expect it to be an attribute on the first item.
            message_length = message_class._EXPECTED_LENGTH
        except AttributeError:
            raise TypeError("No way to know the expected length.  Either pass it as the second member of a tuple or set _EXPECTED_LENGTH on the class you're passing.")

        try:
            kwargs = message_type[2]
        except (IndexError, TypeError):
            kwargs = {}

        return message_class, message_length, kwargs

    def __add__(self, splitter):
        return self.__class__(*self.message_types + splitter.message_types)

    def __radd__(self, other):
        return other + bytes(self)


class RepeatingBytestringSplitter(BytestringSplitter):

    def __call__(self, splittable):
        remainder = True
        messages = []
        while remainder:
            message, remainder = super().__call__(splittable, return_remainder=True)
            messages.append(message)
            splittable = remainder
        return messages


def fingerprint_from_key(public_key: Any):
    """
    Hashes a key using keccak-256 and returns the hexdigest in bytes.
    :return: Hexdigest fingerprint of key (keccak-256) in bytes
    """
    return keccak_digest(bytes(public_key)).hex().encode()
