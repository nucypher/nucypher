import click
from marshmallow import fields
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.cli import types


class String(BaseField, fields.String):
    pass


class List(BaseField, fields.List):
    pass


class Integer(BaseField, fields.Integer):
    click_type = click.INT


class M(Integer):
    pass


class N(Integer):
    pass


class Wei(Integer):
    click_type = types.WEI


class click:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
