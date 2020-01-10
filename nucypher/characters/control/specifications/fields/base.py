import click


class BaseField:

    click_type = click.STRING

    def __init__(self, *args, **kwargs):
        self.click = kwargs.pop('click', None)
        super().__init__(*args, **kwargs)
