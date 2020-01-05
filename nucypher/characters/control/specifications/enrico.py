from .fields import fields
from .base import BaseSchema

class EncryptMessage(BaseSchema):

    message = fields.Str(required=True, load_only=True)
    message_kit = fields.MessageKit(dump_only=True)
    signature = fields.Key(dump_only=True) # maybe we need a signature field?


specifications = {'encrypt_message': EncryptMessage()}
