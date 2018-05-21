"""
Public facing client interface
"""

from nucypher.config.keys import NucypherKeyring


def _bootstrap_config():
    """Do not actually use this."""
    passphrase = input("Enter passphrase >> ")
    return NucypherKeyring.generate(passphrase=passphrase)
