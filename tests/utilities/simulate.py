from twisted.internet import protocol


class UrsulaProcessProtocol(protocol.ProcessProtocol):
    pass


class SimulatedUrsulaProcessProtocol(UrsulaProcessProtocol):
    """Subclass of UrsulaProcessProtocol"""

    def connectionMade(self):
        self.simulate_staking()

    def simulate_staking(self):
        # print("Starting {}".format(self))
        #
        # # Choose random valid stake amount
        # min_stake, balance = int(constants.MIN_ALLOWED_LOCKED), self.ursula.token_balance
        # amount = random.randint(min_stake, balance)
        #
        # # fChoose random valid stake duration in periods
        # min_locktime, max_locktime = int(constants.MIN_LOCKED_PERIODS), int(constants.MAX_MINTING_PERIODS)
        # periods = random.randint(min_locktime, max_locktime)
        #
        # # Stake
        # self.ursula.stake(amount=amount, lock_periods=periods)
        pass