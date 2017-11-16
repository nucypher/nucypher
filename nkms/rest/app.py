from apistar import Include, Route
from apistar.frameworks.wsgi import WSGIApp as App
from apistar.handlers import docs_urls, static_urls


def get_kfrag(kmac):
    return


def create_kfrag(kmac):
    return


routes = [
    Route('/kFrag/{kmac}', 'GET', get_kfrag),
    Route('/kFrag/{kmac}', 'POST', create_kfrag),
    Include('/docs', docs_urls),
    Include('/static', static_urls)
]

app = App(routes=routes)


if __name__ == '__main__':
    app.main(('run',))
