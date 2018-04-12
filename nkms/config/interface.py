"""
Public facing client interface
"""

from nkms.config.keys import KMSKeyring


def _bootstrap_config():
    """Do not actually use this."""
    passphrase = input("Enter passphrase >> ")
    return KMSKeyring.generate(passphrase=passphrase)
