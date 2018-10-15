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
        TODO
        Sends a POST request with the stats collected during runtime.
        """
        if not self.__health_stats:
            # Nothing has been collected, no need to POST anything.
            pass
        raise NotImplementedError

    @property
    def health_stats(self):
        return self.__health_stats
