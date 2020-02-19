from nucypher.characters.control.specifications import fields
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE,
    NETWORK_PORT,
    WEI)

# we update https://github.com/marshmallow-code/apispec/blob/dev/src/apispec/ext/marshmallow/field_converter.py#L26
# with our own custom field types
DEFAULT_FIELD_MAPPING = {
    fields.Integer: ("integer", "int32"),
    fields.Number: ("number", None),
    fields.Float: ("number", "float"),
    fields.Decimal: ("number", None),
    fields.String: ("string", None),
    fields.Boolean: ("boolean", None),
    fields.UUID: ("string", "uuid"),
    fields.DateTime: ("string", "date-iso8601"),
    fields.Date: ("string", "date"),
    fields.Time: ("string", None),
    fields.Email: ("string", "email"),
    fields.URL: ("string", "url"),
    fields.Dict: ("object", None),
    fields.Field: (None, None),
    fields.Raw: (None, None),
    fields.List: ("array", None),
    # custom fields below
    fields.Key: ("string", "key"),
    fields.Label: ("string", None),
    fields.UmbralMessageKit: ("string", "base64"),
    fields.TreasureMap: ("string", "base64"),
    fields.Cleartext: ("string", "textfield"),

    # some from click
    EIP55_CHECKSUM_ADDRESS: ("string", EIP55_CHECKSUM_ADDRESS.name),
    EXISTING_READABLE_FILE: ("file", None),
    NETWORK_PORT: ("integer", NETWORK_PORT.name),
    WEI: ("integer", WEI.name),
}
