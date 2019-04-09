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

from examples.vehicle_data_exchange import alicia, enrico, bob
from examples.vehicle_data_exchange.app import app, cleanup


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
    html.A('ENRICO (OBD DEVICE)', href='/enrico', target='_enrico'),
    html.Br(),
    html.A('INSURER BOB', href='/bob', target='_bob'),
    html.Br(),
    html.Hr(),
    html.H2('Overview'),
    html.Div([
        html.Img(src='/assets/vehicle_demo_overview.png'),
    ], className='overview')
])


@app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/alicia':
        return alicia.layout
    elif pathname == '/enrico':
        return enrico.layout
    elif pathname == '/bob':
        return bob.get_layout()
    else:
        return index_page


if __name__ == '__main__':
    try:
        app.run_server()
    finally:
        cleanup()
