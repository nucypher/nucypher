import click
from marshmallow import fields
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.characters.control.specifications.exceptions import InvalidInputData
from nucypher.cli import types


class String(BaseField, fields.String):
    pass


class List(BaseField, fields.List):
    pass


class Integer(BaseField, fields.Integer):
    click_type = click.INT


class PositiveInteger(Integer):

    def _validate(self, value):
        if not value > 0:
            raise InvalidInputData(f"{self.name} must be a positive integer.")


class M(PositiveInteger):
    pass


class N(PositiveInteger):
    pass


class Wei(Integer):
    click_type = types.WEI


class click:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
