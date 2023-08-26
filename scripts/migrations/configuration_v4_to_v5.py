#!/usr/bin/env python

import sys

from nucypher.config.migrations import configuration_v4_to_v5

if __name__ == "__main__":
    try:
        _python, filepath = sys.argv
    except ValueError:
        raise ValueError('Invalid command: Provide a single configuration filepath.')
    configuration_v4_to_v5(filepath=filepath)
