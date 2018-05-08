"""
Public facing client interface
"""

from nucypher.config.keys import NuCypherKeyring


def _bootstrap_config():
    """Do not actually use this."""
    passphrase = input("Enter passphrase >> ")
    return NuCypherKeyring.generate(passphrase=passphrase)
