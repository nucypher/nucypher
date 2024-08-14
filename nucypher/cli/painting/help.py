import click
from constant_sorrow.constants import NO_KEYSTORE_ATTACHED

from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, USER_LOG_DIR
from nucypher.crypto.powers import RitualisticPower


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(NUCYPHER_BANNER, bold=True)
    ctx.exit()


def echo_config_root_path(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(str(DEFAULT_CONFIG_ROOT.absolute()))
    ctx.exit()


def echo_logging_root_path(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(str(USER_LOG_DIR.absolute()))
    ctx.exit()


def paint_new_installation_help(emitter, new_configuration, filepath):
    character_config_class = new_configuration.__class__
    character_name = character_config_class.NAME.lower()
    if new_configuration.keystore != NO_KEYSTORE_ATTACHED:
        ritual_power = new_configuration.keystore.derive_crypto_power(RitualisticPower)
        ferveo_public_key = bytes(ritual_power.public_key()).hex()
        maybe_public_key = f"{ferveo_public_key[:8]}...{ferveo_public_key[-8:]}"
    else:
        maybe_public_key = "(no keystore attached)"

    emitter.message("Generated keystore", color="green")
    emitter.message(
        f"""

Operator Address:   {new_configuration.wallet_address}
DKG Public Key:   {maybe_public_key}
Path to Keystore: {new_configuration.keystore_dir}
Path to Config:   {filepath}
Path to Logs:     {USER_LOG_DIR}

- Never share your mnemonic with anyone! 
- Secure your mnemonic.  Without it, you *cannot* recover your keys in the event of data loss.
- Regularly backup your keystore directory. This will allow you to recover your keys in the event of data loss.
- Secure your password. Without the password, you will be unable to launch your node.
- The Operator Address must be funded and bonded with a stake in order to run a node.

"""
    )

    if character_name == "ursula":
        hint = """
* Review configuration  -> nucypher ursula config
* Launch node           -> nucypher ursula run
"""

    else:
        raise ValueError(f'Unknown character type "{character_name}"')

    emitter.echo(hint, color='green')
