import cProfile
import os
from pstats import SortKey, Stats


class Profiler(cProfile.Profile):
    """Profiler object for execution statistics."""

    PROFILER_ENV_VAR = "COLLECT_PROFILER_STATS"

    def __init__(
        self,
        label: str = "",
        sort_by: SortKey = SortKey.TIME,
        top_n_entries: int = 10,
        **kwargs,
    ) -> None:
        self.active = self.PROFILER_ENV_VAR in os.environ
        self.label = label
        self.top_n = top_n_entries
        self.sort_by = sort_by
        super().__init__(**kwargs)

    def __enter__(self):
        if self.active:
            super().__enter__()
        return self

    def __exit__(self, *exc_info):
        if self.active:
            super().__exit__(exc_info)
            profiler_stats = Stats(self).sort_stats(self.sort_by)
            label = f"[{self.label}]" if self.label else ""
            print(f"\n------ Profile Stats {label} -------")
            profiler_stats.print_stats(self.top_n)
            print(f"\n- Caller Info {label} -")
            profiler_stats.print_callers(self.top_n)
