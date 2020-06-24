"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import msgpack
from typing import Any, Callable, Iterable, NamedTuple, Optional, Union


class DBWriteError(Exception):
    """
    Exception class for when db writes fail.
    """
    pass


class RecordField(NamedTuple):
    field_type: Any
    encode: Optional[Callable] = lambda field: field
    decode: Optional[Callable] = lambda field: field


class DatastoreRecord:
    def __new__(cls, *args, **kwargs):
        # Set default class attributes for the new instance
        cls.__writeable = None
        cls.__storagekey = f'{cls.__name__}:{{record_field}}:{{record_id}}'
        return super().__new__(cls)

    def __init__(self,
                 db_tx: 'lmdb.Transaction',
                 record_id: Union[int, str],
                 writeable: bool = False) -> None:
        self._record_id = record_id
        self._fields = [field[1:] for field in type(self).__dict__ if type(type(self).__dict__[field]) == RecordField]
        self.__db_tx = db_tx
        self.__writeable = writeable

    def __setattr__(self, attr: str, value: Any) -> None:
        """
        This method is called when setting attributes on the class. We override
        this method to serialize the value being set to the attribute, and then
        we _write_ it to the database.

        When `__writeable` is `None`, we only set attributes on the instance.
        When `__writeable` is `False`, we raise a `TypeError`.

        Finally, when `__writeable` is `True`, we get the `RecordField` for
        the corresponding `attr` and check that the `value` being set is
        the correct type via its `RecordField.field_type`. If the type is not
        correct, we raise a `TypeError`.

        If the type is correct, we then serialize it to bytes via its
        `RecordField.encode` function and pack it with msgpack. Then the value
        gets written to the database. If the value is unable to be written,
        this will raise a `DBWriteError`.
        """
        # When writeable is None (meaning, it hasn't been __init__ yet), then
        # we allow any attribute to be set on the instance.
        # HOT LAVA -- causes a recursion if this check isn't present.
        if self.__writeable is None:
            super().__setattr__(attr, value)

        # Datastore records are not writeable/mutable by default, so we
        # raise a TypeError in the event that writeable is False.
        elif self.__writeable is False:
            raise TypeError("This datastore record isn't writeable.")

        # A datastore record is only mutated iff writeable is True.
        elif self.__writeable is True:
            record_field = self.__get_record_field(attr)
            if not type(value) == record_field.field_type:
                raise TypeError(f'Given record is type {type(value)}; expected {record_field.field_type}')
            field_value = msgpack.packb(record_field.encode(value))
            self.__write_raw_record(attr, field_value)

    def __getattr__(self, attr: str) -> Any:
        """
        This method is called when accessing attributes that don't exist on the
        class. We override this method to _read_ from the database and return
        a deserialized record.

        We deserialize records by calling the record's respective `RecordField.decode`
        function. If the deserialized type doesn't match the type defined by
        its `RecordField.field_type`, then this method will raise a `TypeError`.
        """
        # Handle __getattr__ look ups for private fields
        # HOT LAVA -- causes a recursion if this check isn't present.
        if attr.startswith('_'):
            return super().__getattr__(attr)

        # Get the corresponding RecordField and retrieve the raw value from
        # the db, unpack it, then use the `RecordField` to deserialize it.
        record_field = self.__get_record_field(attr)
        field_value = record_field.decode(msgpack.unpackb(self.__retrieve_raw_record(attr)))
        if not type(field_value) == record_field.field_type:
            raise TypeError(f"Decoded record was type {type(field_value)}; expected {record_field.field_type}")
        return field_value

    def __retrieve_raw_record(self, record_field: str) -> bytes:
        """
        Retrieves a raw record, as bytes, from the database given a `record_field`.
        If the record doesn't exist, this method raises an `AttributeError`.
        """
        key = self.__storagekey.format(record_field=record_field, record_id=self._record_id).encode()
        field_value = self.__db_tx.get(key, default=None)
        if field_value is None:
            raise AttributeError(f"No {record_field} record found for ID: {self._record_id}.")
        return field_value

    def __write_raw_record(self, record_field: str, value: bytes) -> None:
        """
        Writes a raw record, as bytes, to the database given a `record_field`
        and a `value`.
        If the record is unable to be written, this method raises a `DBWriteError`.
        """
        key = self.__storagekey.format(record_field=record_field, record_id=self._record_id).encode()
        if not self.__db_tx.put(key, value, overwrite=True):
            raise DBWriteError("Couldn't write the record to the database.")

    def __get_record_field(self, attr: str) -> 'RecordField':
        """
        Uses `getattr` to return the `RecordField` object for a given
        attribute.
        These objects are accessed via class attrs as `_{attribute}`. If the
        `RecordField` doesn't exist for a given `attr`, then this method will
        raise a `TypeError`.
        """
        try:
            record_field = getattr(self, f'_{attr}')
        except AttributeError:
            raise TypeError(f'No valid RecordField found on {self} for {attr}.')
        return record_field
