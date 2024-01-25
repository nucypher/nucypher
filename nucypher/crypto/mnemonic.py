import click
from eth_account.hdaccount import Mnemonic

from nucypher.utilities.emitters import StdoutEmitter

_WORD_COUNT = 24
_LANGUAGE = "english"


def _generate(interactive: bool) -> str:
    __words = Mnemonic(raw_language=_LANGUAGE).generate(num_words=_WORD_COUNT)
    if interactive:
        _confirm(__words)
    return __words


def _confirm(__words: str) -> None:
    """
    Inform the caller of new keystore seed words generation the console
    and optionally perform interactive confirmation.
    """

    # notification
    emitter = StdoutEmitter()
    emitter.message(
        "Backup your seed words, you will not be able to view them again.\n"
    )
    emitter.message(f"{__words}\n", color="cyan")
    if not click.confirm("Have you backed up your seed phrase?"):
        emitter.message('Keystore generation aborted.', color='red')
        raise click.Abort()
    click.clear()

    # confirmation
    __response = click.prompt("Confirm seed words")
    if __response != __words:
        raise ValueError('Incorrect seed words confirmation. No keystore has been created, try again.')
    click.clear()
