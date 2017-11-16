from typing import Dict, List


def read_config() -> Dict:
    """
    Reads the config data from config.yaml.

    :return: The parsed yaml config data in a dict
    """
    from yaml import load
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader

    with open('config.yaml') as f:
        config_data = f.read()

    return load(config_data, Loader=Loader)


def check_config_errors(config: Dict) -> List[str]:
    """
    Checks that the config file has expected values.

    :param config: The parsed yaml config file (config.yaml)

    :return: A List of the errors.
    """
    errors = []

    if 'owner_key' not in config:
        errors += "ROOT ERROR: No entry for `owner_key` found."
    else:
        # Check keyfile entry
        if 'keyfile' not in config['owner_key']:
            errors += "OWNER_KEY ERROR: No entry for `keyfile` found."
        elif config['owner_key']['keyfile'] == "":
            errors += "OWNER_KEY ERROR: `keyfile` path cannot be empty."

        # Check fingerprint entry
        if 'fingerprint' not in config['owner_key']['fingerprint']:
            errors += "OWNER_KEY ERROR: `No entry for `fingerprint` found."
        elif config['owner_key']['fingerprint'] == "":
            errors += "OWNER_KEY ERROR: `fingerprint` cannot be empty."
    return errors
