class NuCypherTokenConfig:
    __subdigits = 18
    _M = 10 ** __subdigits                                 # Unit designation
    __initial_supply = int(1e9) * _M                       # Initial token supply
    __saturation = int(3.89e9) * _M                        # Token supply cap
    _remaining_supply = __saturation - __initial_supply    # Remaining supply

    @property
    def saturation(self):
        return self.__saturation


class NuCypherMinerConfig:
    _hours_per_period = 24       # Hours in single period
    _min_release_periods = 30    # 720 Hours minimum
    __max_minting_periods = 365  # Maximum number of periods

    _min_allowed_locked = 15000 * NuCypherTokenConfig._M
    _max_allowed_locked = int(4e6) * NuCypherTokenConfig._M

    _null_addr = '0x' + '0' * 40
    __remaining_supply = NuCypherTokenConfig._remaining_supply

    __mining_coeff = [           # TODO
        _hours_per_period,
        2 * 10 ** 7,
        __max_minting_periods,
        __max_minting_periods,
        _min_release_periods,
        _min_allowed_locked,
        _max_allowed_locked
    ]

    @property
    def null_address(self):
        return self._null_addr

    @property
    def mining_coefficient(self):
        return self.__mining_coeff

    @property
    def remaining_supply(self):
        return self.__remaining_supply
