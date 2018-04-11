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

    @property
    def null_address(self):
        return self._null_addr

    @property
    def mining_coefficient(self):
        return self.__mining_coeff

    @property
    def reward(self):
        return self.__reward
