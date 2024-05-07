import click

from nucypher.utilities.logging import Logger


class StdoutEmitter:

    default_color = 'white'

    def __init__(self,
                 verbosity: int = 1):

        self.name = self.__class__.__name__.lower()
        self.verbosity = verbosity
        self.log = Logger(self.name)

    def clear(self):
        if self.verbosity >= 1:
            click.clear()

    def message(self,
                message: str,
                color: str = None,
                bold: bool = False,
                verbosity: int = 1):
        self.echo(message, color=color or self.default_color, bold=bold, verbosity=verbosity)
        # these are application messages that are desired to be
        #  printed to stdout (with or w/o console logging); send to logger
        if verbosity > 1:
            self.log.debug(message)
        else:
            self.log.info(message)

    def echo(self,
             message: str = None,
             color: str = None,
             bold: bool = False,
             nl: bool = True,
             verbosity: int = 0):
        # these are user interactions; don't send to logger
        if verbosity <= self.verbosity:
            click.secho(message=message, fg=color or self.default_color, bold=bold, nl=nl)

    def banner(self, banner):
        # these are purely for banners; don't send to logger
        if self.verbosity >= 1:
            click.echo(banner)

    def error(self, e):
        e_str = str(e)
        if self.verbosity >= 1:
            click.echo(message=e_str, color="red")
        # some kind of error; send to logger
        self.log.error(e_str)
