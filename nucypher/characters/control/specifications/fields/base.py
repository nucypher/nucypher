import click


class BaseField:

    click_type = click.STRING

    def __init__(self, *args, **kwargs):
        self.click = kwargs.pop('click', None)
        if self.click:
            self.click.kwargs['required'] = kwargs.get('required', False)
            self.click.kwargs['type'] = self.click_type
        super().__init__(*args, **kwargs)
