import click

class BaseField:

    type_hint = ("string", None)

    def __init__(self, *args, **kwargs):
        self.click = kwargs.pop('click', None)
        super().__init__(*args, **kwargs)
