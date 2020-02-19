import click

class BaseField:

    def __init__(self, *args, **kwargs):
        self.click = kwargs.pop('click', None)
        super().__init__(*args, **kwargs)
