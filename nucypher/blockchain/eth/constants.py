NULL_ADDRESS = '0x' + '0' * 40


class NucypherTokenConstants:

    class TokenConfigError(ValueError):
        pass

    __subdigits = 18
    _M = 10 ** __subdigits                                 # Unit designation
    __initial_supply = int(1e9) * _M                       # Initial token supply
    __saturation = int(3.89e9) * _M                        # Token supply cap
    _remaining_supply = __saturation - __initial_supply    # Remaining supply

    @property
    def saturation(self):
        return self.__saturation

    @property
    def M(self):
        return self._M


class NucypherMinerConstants:

    class MinerConfigError(ValueError):
        pass

    _hours_per_period = 24       # Hours in single period
    min_locked_periods = 30      # 720 Hours minimum
    max_minting_periods = 365    # Maximum number of periods

    min_allowed_locked = 15000 * NucypherTokenConstants._M
    max_allowed_locked = int(4e6) * NucypherTokenConstants._M

    __remaining_supply = NucypherTokenConstants._remaining_supply

    __mining_coeff = [           # TODO
        _hours_per_period,
        2 * 10 ** 7,
        max_minting_periods,
        max_minting_periods,
        min_locked_periods,
        min_allowed_locked,
        max_allowed_locked
    ]

    @property
    def mining_coefficient(self):
        return self.__mining_coeff

    @property
    def remaining_supply(self):
        return self.__remaining_supply

    def __validate(self, rulebook) -> bool:
        for rule, failure_message in rulebook:
            if not rule:
                raise self.MinerConfigError(failure_message)
        return True

    def validate_stake_amount(self, amount: int, raise_on_fail=True) -> bool:

        rulebook = (

            (amount >= self.min_allowed_locked,
             'Stake amount too low; ({amount}) must be at least {minimum}'
             .format(minimum=self.min_allowed_locked, amount=amount)),

            (amount <= self.max_allowed_locked,
             'Stake amount too high; ({amount}) must be no more than {maximum}.'
             .format(maximum=self.max_allowed_locked, amount=amount)),
        )

        if raise_on_fail is True:
            self.__validate(rulebook=rulebook)
        return all(rulebook)

    def validate_locktime(self, lock_periods: int, raise_on_fail=True) -> bool:

        rulebook = (

            (lock_periods >= self.min_locked_periods,
             'Locktime ({locktime}) too short; must be at least {minimum}'
             .format(minimum=self.min_locked_periods, locktime=lock_periods)),

            (lock_periods <= self.max_minting_periods,
             'Locktime ({locktime}) too long; must be no more than {maximum}'
             .format(maximum=self.max_minting_periods, locktime=lock_periods)),
        )

        if raise_on_fail is True:
            self.__validate(rulebook=rulebook)
        return all(rulebook)
