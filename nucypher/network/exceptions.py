import requests, socket

NodeSeemsToBeDown = (requests.exceptions.ConnectionError,
                     requests.exceptions.ReadTimeout,
                     socket.gaierror,
                     ConnectionRefusedError)
