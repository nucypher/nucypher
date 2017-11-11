

class BytestringSplitter(object):

    def __init__(self, *message_types):
        """
        :param message_types:  A collection of types of messages to parse.
        """
        self.message_types = message_types

    def __call__(self, splittable):
        if self.total_expected_length() != len(splittable):
            raise ValueError("Wrong number of bytes to constitute message types {} - need {}, got {}".format(self.message_types, self.total_expected_length(), len(splittable)))

        cursor = 0
        message_objects = []

        for message_type in self.message_types:
            expected_end_of_object_bytes = cursor + message_type._EXPECTED_LENGTH
            bytes_for_this_object = splittable[cursor:cursor + expected_end_of_object_bytes]
            message_objects.append(message_type(bytes_for_this_object))
            cursor = expected_end_of_object_bytes

        return message_objects

    def total_expected_length(self):
        return sum(m._EXPECTED_LENGTH for m in self.message_types)
