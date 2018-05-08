import json
import os
import stat

from .configs import _DEFAULT_CONFIGURATION_DIR, NuCypherConfigurationError


def _save_private_keyfile(keypath: str, key_data: dict) -> str:
    """
    Creates a permissioned keyfile and save it to the local filesystem.
    The file must be created in this call, and will fail if the path exists.
    Returns the filepath string used to write the keyfile.

    Note: getting and setting the umask is not thread-safe!

    See linux open docs: http://man7.org/linux/man-pages/man2/open.2.html
    ---------------------------------------------------------------------
    O_CREAT - If pathname does not exist, create it as a regular file.


    O_EXCL - Ensure that this call creates the file: if this flag is
             specified in conjunction with O_CREAT, and pathname already
             exists, then open() fails with the error EEXIST.
    ---------------------------------------------------------------------
    """

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
    mode = stat.S_IRUSR | stat.S_IWUSR              # 0o600

    try:
        keyfile_descriptor = os.open(path=keypath, flags=flags, mode=mode)
    finally:
        os.umask(0)  # Set the umask to 0 after opening

    # Write and destroy file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        keyfile.write(json.dumps(key_data))
        output_path = keyfile.name

    # TODO: output_path is an integer, who knows why?
    del keyfile_descriptor
    return output_path


def _save_public_keyfile(keypath: str, key_data: bytes) -> str:
    """
    Creates a permissioned keyfile and save it to the local filesystem.
    The file must be created in this call, and will fail if the path exists.
    Returns the filepath string used to write the keyfile.

    Note: getting and setting the umask is not thread-safe!

    See Linux open docs: http://man7.org/linux/man-pages/man2/open.2.html
    ---------------------------------------------------------------------
    O_CREAT - If pathname does not exist, create it as a regular file.


    O_EXCL - Ensure that this call creates the file: if this flag is
             specified in conjunction with O_CREAT, and pathname already
             exists, then open() fails with the error EEXIST.
    ---------------------------------------------------------------------
    """

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL    # Write, Create, Non-Existing
    mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH # 0o644

    try:
        keyfile_descriptor = os.open(path=keypath, flags=flags, mode=mode)
    finally:
        os.umask(0) # Set the umask to 0 after opening

    # Write and destroy the file descriptor reference
    with os.fdopen(keyfile_descriptor, 'wb') as keyfile:
        # key data should be urlsafe_base64
        keyfile.write(key_data)
        output_path = keyfile.name

    # TODO: output_path is an integer, who knows why?
    del keyfile_descriptor
    return output_path


def _parse_keyfile(keypath: str):
    """Parses a keyfile and returns key metadata as a dict."""

    with open(keypath, 'r') as keyfile:
        try:
            key_metadata = json.loads(keyfile)
        except json.JSONDecodeError:
            raise NuCypherConfigurationError("Invalid data in keyfile {}".format(keypath))
        else:
            return key_metadata


def generate_confg_dir(path: str=None,) -> None:
    """
    Create the configuration directory tree.
    If the directory already exists, FileExistsError is raised.
    """
    path = path if path else _DEFAULT_CONFIGURATION_DIR

    if not os.path.exists(path):
        os.mkdir(path, mode=0o755)


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise NuCypherConfigurationError(failure_message)
    return True


def check_config_tree(configuration_dir: str=None) -> bool:
    path = configuration_dir if configuration_dir else _DEFAULT_CONFIGURATION_DIR
    if not os.path.exists(path):
        raise FileNotFoundError('No NuCypher configuration directory found at {}.'.format(configuration_dir))
    return True


def check_config_runtime() -> bool:
    rules = (
        (os.getuid() != 0, 'Cannot run as root user.'),

    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


