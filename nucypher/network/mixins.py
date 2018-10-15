class HealthMonitorMixin:
    """
    A Mixin for monitoring the health of the NuCypher network. This operates as
    opt-in behavior. Users may disable certain stats in a config (TODO), if they
    prefer. Nothing sensitive is collected here and all information is
    anonymous.
    """

    def __init__(self):
        self.__health_stats = {}

    def post_stats(self):
        """
        TODO: Implement this method
        Sends a POST request with the stats collected during runtime.
        """
        # TODO: Only POST stats if health monitoring enabled
        if not self.__health_stats:
            # Nothing has been collected, no need to POST anything.
            pass
        raise NotImplementedError

    @property
    def health_stats(self):
        # TODO: Find a more reasonable interface for this to prevent arbitrary
        # information being added to the stats log.
        return self.__health_stats
