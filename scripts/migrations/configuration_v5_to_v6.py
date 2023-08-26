#!/usr/bin/env python

import sys

from nucypher.config.migrations import configuration_v5_to_v6

if __name__ == "__main__":
    try:
        _python, filepath = sys.argv
    except ValueError:
        raise ValueError("Invalid command: Provide a single configuration filepath.")
    configuration_v5_to_v6(filepath=filepath)
