from enum import Enum
from os.path import dirname, join, abspath

import appdirs
import populus

import nkms_eth


class NuCypherTokenConfig:
    __subdigits = 18
    _M = 10 ** __subdigits
    __premine = int(1e9) * _M
    __saturation = int(1e10) * _M
    _reward = __saturation - __premine

    @property
    def saturation(self):
        return self.__saturation


class NuCypherMinerConfig:
    _hours_per_period = 24       # Hours
    _min_release_periods = 30    # 720 Hours
    __max_awarded_periods = 365

    __min_allowed_locked = 10 ** 6
    __max_allowed_locked = 10 ** 7 * NuCypherTokenConfig._M

    _null_addr = '0x' + '0' * 40
    __reward = NuCypherTokenConfig._reward

    __mining_coeff = [
        _hours_per_period,
        2 * 10 ** 7,
        __max_awarded_periods,
        __max_awarded_periods,
        _min_release_periods,
        __min_allowed_locked,
        __max_allowed_locked
    ]

    class MinerInfoField(Enum):
        MINERS_LENGTH = 0
        MINER = 1
        VALUE = 2
        DECIMALS = 3
        LOCKED_VALUE = 4
        RELEASE = 5
        MAX_RELEASE_PERIODS = 6
        RELEASE_RATE = 7
        CONFIRMED_PERIODS_LENGTH = 8
        CONFIRMED_PERIOD = 9
        CONFIRMED_PERIOD_LOCKED_VALUE = 10
        LAST_ACTIVE_PERIOD_F = 11
        DOWNTIME_LENGTH = 12
        DOWNTIME_START_PERIOD = 13
        DOWNTIME_END_PERIOD = 14
        MINER_IDS_LENGTH = 15
        MINER_ID = 16

    @property
    def null_address(self):
        return self._null_addr


    @property
    def mining_coefficient(self):
        return self.__mining_coeff

    @property
    def reward(self):
        return self.__reward


class PopulusConfig:

    def __init__(self, project_name='nucypher-kms', registrar_path=None):
        self._python_project_name = project_name

        # This config is persistent and is created in user's .local directory
        if registrar_path is None:
            registrar_path = join(appdirs.user_data_dir(self._python_project_name), 'registrar.json')
        self._registrar_path = registrar_path

        # Populus project config
        self._project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        self._populus_project = populus.Project(self._project_dir)
        self.project.config['chains.mainnetrpc.contracts.backends.JSONFile.settings.file_path'] = self._registrar_path

    @property
    def project(self):
        return self._populus_project
