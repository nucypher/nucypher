import requests, socket

NodeSeemsToBeDown = (requests.exceptions.ConnectionError,
                     requests.exceptions.ReadTimeout,
                     requests.exceptions.ConnectTimeout,
                     socket.gaierror,
                     ConnectionRefusedError)
