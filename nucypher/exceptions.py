# Package Warnings #
####################


class DevelopmentInstallationRequired(RuntimeError):
    MESSAGE = """
    A development installation of nucypher is required to import {importable_name}.
    """

    def __init__(self, importable_name: str, *args, **kwargs):
        msg = self.MESSAGE.format(importable_name=importable_name)
        super().__init__(msg, *args, **kwargs)
