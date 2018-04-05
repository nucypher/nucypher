import sys
from .configs import validate_passphrase, KMSConfig

# Configurator Text #

title = "NuCypher KMS Configurator"
welcome = "Welcome to the NuCypher KMS Config Tool"
description = "Use this tool to manage keypairs node operation."

newlines = '\n' * 2
press_any = "Press any key to continue..."

enter_new_passphrase = 'Enter new passphrase: '
confirm_passphrase = "Confirm passphrase"
did_not_match = "Passwords did not match"

loading = "loading..."
keygen_success = "Keys generated and written to keyfile!"


def close():
    sys.exit()


def gather_passphrase():
    user_passphrase = input(enter_new_passphrase)

    try:    # Validate
        validate_passphrase(user_passphrase)
    except KMSConfig.KMSConfigrationError:
        close()
    else:
        confirm_passphrase = input(enter_new_passphrase)
        if user_passphrase != confirm_passphrase:
            print(did_not_match)
            del user_passphrase
            del confirm_passphrase
            gather_passphrase()

    return user_passphrase


def start():
    print(title, welcome, description, newlines, sep='\n')
    input(press_any)
    gather_passphrase()


start()
