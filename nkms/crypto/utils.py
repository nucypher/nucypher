import msgpack


class BytestringSplitter(object):
    def __init__(self, *message_types):
        """
        :param message_types:  A collection of types of messages to parse.
        """
        self.message_types = message_types

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
            message_length = message_type[1]
        except TypeError:
            message_length = message_type._EXPECTED_LENGTH
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
