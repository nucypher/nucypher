


class IsType:
    def __init__(self, expected_type):
        self.expected_type = expected_type

    def __eq__(self, other):
        return isinstance(other, self.expected_type)

    def __repr__(self):
        return f'<IsType({self.expected_type})>'
