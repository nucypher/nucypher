import requests
import socket

NodeSeemsToBeDown = (requests.exceptions.ConnectionError,
                     requests.exceptions.ReadTimeout,
                     socket.gaierror,
                     ConnectionRefusedError)
