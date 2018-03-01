from typing import Dict


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
