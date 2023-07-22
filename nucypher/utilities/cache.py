from threading import RLock
from typing import Dict, Optional

import maya


class TTLCache:
    """
    Thread-safe cache that stores keyed data with auto-expiring values via a time-to-live.

    Expired items are not proactively removed from the cache unless functionality
    necessitates it. Either specific items get proactively removed for example trying
    to access a keyed-value that is already expired, OR a wholistic purge occurs because
    consistent global state is needed, for example, the length of the cache queried or
    a list of key-value pairs requested.

    Expired entries can be forcibly purged at any time using the purge_expired() function.
    """

    class TTLEntry:
        def __init__(self, value: object, ttl: int):
            self._value = value
            self._expiration = maya.now().add(seconds=ttl)

        @property
        def value(self) -> Optional[object]:
            """
            Return the value if not expired, None otherwise
            """
            if self.is_expired():
                return None

            return self._value

        def is_expired(self) -> bool:
            """
            Return true if the entry has exceeded its time-to-live.
            """
            return self._expiration < maya.now()

    def __init__(self, ttl: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if ttl <= 0:
            raise ValueError(f"Invalid time-to-live {ttl}")
        self.ttl = ttl
        self.__cache: Dict[object, TTLCache.TTLEntry] = {}
        self.__cache_lock = RLock()

    def __setitem__(self, key, value):
        """
        Add the provided key entry to be the provided value.
        """
        if key is None or value is None:
            raise ValueError(f"Invalid key-value pair ({key}, {value})")

        with self.__cache_lock:
            self.__cache[key] = self.TTLEntry(value=value, ttl=self.ttl)

    def __getitem__(self, key):
        """
        Return the associated keyed item, else None if expired or not present.
        """
        with self.__cache_lock:
            ttl_entry = self.__cache.get(key)
            if not ttl_entry:
                # no value stored
                return None

            value = ttl_entry.value
            if not value:
                # entry is expired
                del self.__cache[key]
                return None

            return value

    def items(self):
        """
        Returns a copy of the cache's list of non-expired (key, value) pairs.
        """
        key_value_pairs = []
        with self.__cache_lock:
            for key in list(self.__cache):
                ttl_entry = self.__cache[key]
                value = ttl_entry.value
                if value:
                    key_value_pairs.append((key, ttl_entry.value))
                else:
                    # expired entry, opportunity to remove it
                    del self.__cache[key]

        return key_value_pairs

    def pop(self, key, default=None):
        """
        Get item from the cache and remove it.
        Return default if expired or does not exist.
        """
        with self.__cache_lock:
            ttl_entry = self.__cache.get(key)
            if not ttl_entry:
                return default

            del self.__cache[key]
            value = ttl_entry.value
            if not value:
                # entry expired
                return default

            return value

    def remove(self, key):
        """
        Remove keyed item from the cache.
        """
        with self.__cache_lock:
            if key in self.__cache:
                del self.__cache[key]

    def purge_expired(self):
        """
        Remove all expired items from the cache.
        """
        with self.__cache_lock:
            for key in list(self.__cache):
                entry = self.__cache[key]
                if entry.is_expired():
                    del self.__cache[key]

    def __len__(self):
        """
        Returns the current (non-expired entries) size of the cache.
        """
        with self.__cache_lock:
            self.purge_expired()
            return len(self.__cache)

    def clear(self):
        """
        Remove all items from the cache.
        """
        with self.__cache_lock:
            self.__cache.clear()
