if __name__ == "__main__":
    from sys import path
    from os.path import dirname, abspath
    # We use dirname() to help get the parent directory to add to
    # sys.path, so that we can import the current package.  This is necessary
    # since when invoked directly, the 'current' package is not automatically
    # imported.
    parent_dir = dirname(dirname(dirname(abspath(__file__))))
    path.insert(1, parent_dir)


import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

from examples.heartbeat_demo.rest_ui import enrico, bob, alicia
from examples.heartbeat_demo.rest_ui.app import app, cleanup


app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

index_page = html.Div([
    html.Div([
        html.Img(src='/assets/nucypher_logo.png'),
    ], className='banner'),
    html.A('ALICIA', href='/alicia', target='_alicia'),
    html.Br(),
    html.A('ENRICO (HEART_MONITOR)', href='/enrico', target='_enrico'),
    html.Br(),
    html.A('BOB', href='/bob', target='_bob'),
    html.Br(),
    html.Hr(),
    html.H2('Overview'),
    html.Div([
        html.Img(src='/assets/heartbeat_demo_overview.png'),
    ], className='overview')
])

# This is used to ensure that the first Bob is the 'Doctor'
# Subsequent Bob's can be other professions eg. Nutritionist, Dietitian etc.
first_bob_already_created = list()


@app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/alicia':
        return alicia.layout
    elif pathname == '/enrico':
        return enrico.layout
    elif pathname == '/bob':
        if not first_bob_already_created:
            first_bob_already_created.append(True)
            return bob.get_layout(True)
        else:
            return bob.get_layout(False)
    else:
        return index_page


if __name__ == '__main__':
    try:
        app.run_server()
    finally:
        cleanup()
