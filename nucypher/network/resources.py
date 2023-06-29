

import os

from hendrix.facilities.resources import MediaResource


def get_static_resources():
    resources = []
    if os.getenv('NUCYPHER_STATIC_FILES_ROOT'):
        resources.append(MediaResource(os.getenv('NUCYPHER_STATIC_FILES_ROOT').encode(), namespace=b'statics'))
    return resources
