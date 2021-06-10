.. _porter:

Porter
======

Overview
--------

NuCypher Porter can be described as the *“Infura for NuCypher”*. Porter is a web-based service that performs
nucypher-based protocol operations on behalf of applications.

Its goal is to simplify and abstract the complexities surrounding the nucypher protocol to negate the need for
applications to interact with it via a python client. Porter introduces the nucypher protocol to cross-platform
functionality including web and mobile applications. By leveraging ``rust-umbral`` and its associated javascript
bindings for cryptography, and Porter for communication with the network, a lightweight, richer and full-featured
web and mobile experience is accessible to application developers.

.. image:: ../.static/img/porter_diagram.svg
    :target: ../.static/img/porter_diagram.svg
