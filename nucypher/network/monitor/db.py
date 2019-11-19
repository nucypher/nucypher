import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta

from influxdb import InfluxDBClient
from maya import MayaDT

from nucypher.config.storages import SQLiteForgetfulNodeStorage
from typing import List, Dict


class NetworkCrawlerDBClient:
    """
    Performs operations on data in the NetworkCrawler DB.

    Helpful for data intensive long-running graphing calculations on historical data.
    """
    def __init__(self, host, port, database):
        self._client = InfluxDBClient(host=host, port=port, database=database)

    def get_historical_locked_tokens_over_range(self, days: int):
        today = datetime.utcnow()
        range_end = datetime(year=today.year, month=today.month, day=today.day,
                             hour=0, minute=0, second=0, microsecond=0)
        range_begin = range_end - timedelta(days=days-1)
        results = list(self._client.query(f"SELECT SUM(locked_stake) "
                                          f"FROM ("
                                          f"SELECT staker_address, current_period, "
                                          f"LAST(locked_stake) "
                                          f"AS locked_stake "
                                          f"FROM moe_network_info "
                                          f"WHERE time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' "
                                          f"AND "
                                          f"time < '{MayaDT.from_datetime(range_end + timedelta(days=1)).rfc3339()}' "
                                          f"GROUP BY staker_address, time(1d)"
                                          f") "
                                          f"GROUP BY time(1d)").get_points())

        # Note: all days may not have values eg. days before DB started getting populated
        # As time progresses this should be less of an issue
        locked_tokens_dict = OrderedDict()
        for r in results:
            locked_stake = r['sum']
            if locked_stake:
                # Dash accepts datetime objects for graphs
                locked_tokens_dict[MayaDT.from_rfc3339(r['time']).datetime()] = locked_stake

        return locked_tokens_dict

    def get_historical_num_stakers_over_range(self, days: int):
        today = datetime.utcnow()
        range_end = datetime(year=today.year, month=today.month, day=today.day,
                             hour=0, minute=0, second=0, microsecond=0)
        range_begin = range_end - timedelta(days=days - 1)
        results = list(self._client.query(f"SELECT COUNT(staker_address) FROM "
                                          f"("
                                            f"SELECT staker_address, LAST(locked_stake)"
                                            f"FROM moe_network_info WHERE "
                                            f"time >= '{MayaDT.from_datetime(range_begin).rfc3339()}' AND "
                                            f"time < '{MayaDT.from_datetime(range_end + timedelta(days=1)).rfc3339()}' "
                                            f"GROUP BY staker_address, time(1d)"
                                          f") "
                                          "GROUP BY time(1d)").get_points())   # 1 day measurements

        # Note: all days may not have values eg. days before DB started getting populated
        # As time progresses this should be less of an issue
        num_stakers_dict = OrderedDict()
        for r in results:
            locked_stake = r['count']
            if locked_stake:
                # Dash accepts datetime objects for graphs
                num_stakers_dict[MayaDT.from_rfc3339(r['time']).datetime()] = locked_stake

        return num_stakers_dict

    def close(self):
        self._client.close()


class NodeMetadataDBClient:

    def __init__(self, db_filepath: str = SQLiteForgetfulNodeStorage.DEFAULT_DB_FILEPATH):
        self._db_filepath = db_filepath

    def get_known_nodes_metadata(self) -> Dict:
        # dash threading means that connection needs to be established in same thread as use
        db_conn = sqlite3.connect(self._db_filepath)
        try:
            result = db_conn.execute(f"SELECT * FROM {SQLiteForgetfulNodeStorage.NODE_DB_NAME}")

            # TODO use `pandas` package instead to automatically get dict?
            known_nodes = dict()
            column_names = [description[0] for description in result.description]
            for row in result:
                node_info = dict()
                staker_address = row[0]
                for idx, value in enumerate(row):
                    node_info[column_names[idx]] = row[idx]
                known_nodes[staker_address] = node_info

            return known_nodes
        finally:
            db_conn.close()

    def get_previous_states_metadata(self, limit: int = 5) -> List[Dict]:
        # dash threading means that connection needs to be established in same thread as use
        db_conn = sqlite3.connect(self._db_filepath)
        states_dict_list = []
        try:
            result = db_conn.execute(f"SELECT * FROM {SQLiteForgetfulNodeStorage.STATE_DB_NAME} "
                                     f"ORDER BY datetime(updated) DESC LIMIT {limit}")

            # TODO use `pandas` package instead to automatically get dict?
            column_names = [description[0] for description in result.description]
            for row in result:
                state_info = dict()
                for idx, value in enumerate(row):
                    column_name = column_names[idx]
                    if column_name == 'updated':
                        # convert column from rfc3339 (for sorting) back to rfc2822
                        # TODO does this matter for displaying?
                        state_info[column_name] = MayaDT.from_rfc3339(row[idx]).rfc2822()
                    else:
                        state_info[column_name] = row[idx]
                states_dict_list.append(state_info)

            return states_dict_list
        finally:
            db_conn.close()
