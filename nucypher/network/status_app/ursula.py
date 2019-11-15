import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input

from nucypher.characters.base import Character
from nucypher.network.status_app.base import NetworkStatusPage


class UrsulaStatusApp(NetworkStatusPage):
    """
    Status application for Ursula node.
    """

    def __init__(self, ursula: Character, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dash_app.assets_ignore = 'hendrix-update.js'  # javascript not needed for Ursula
        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='header'),
            html.Div(id='ursula_info'),
            html.Div(id='domains'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            # use a periodic update interval (every 2s) instead of notification updates from hendrix used by Moe
            dcc.Interval(id='status-update', interval=2000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header()

        @self.dash_app.callback(Output('ursula_info', 'children'), [Input('url', 'pathname')])  # on page-load
        def ursula_info(pathname):
            info = html.Div([
                html.Div([
                    html.H4('Icon', className='one column'),
                    html.Div([
                        html.Span(f'{ursula.nickname_metadata[0][1]}', className='single-symbol'),
                        html.Span(f'{ursula.nickname_metadata[1][1]}', className='single-symbol'),
                    ], className='symbols three columns'),

                ], className='row'),
            ], className='row')
            return info

        @self.dash_app.callback(Output('domains', 'children'), [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = ' | '.join(ursula.learning_domains)
            return html.Div([
                html.H4('Domains', className='one column'),
                html.H5(domains, className='eleven columns'),
            ], className='row')

        @self.dash_app.callback(Output('prev-states', 'children'), [Input('status-update', 'n_intervals')])
        def state(n):
            """Simply update periodically"""
            return self.previous_states(ursula)

        @self.dash_app.callback(Output('known-nodes', 'children'), [Input('status-update', 'n_intervals')])
        def known_nodes(n):
            """Simply update periodically"""
            teacher = ursula.current_teacher_node()
            teacher_checksum = None
            if teacher:
                teacher_checksum = teacher.checksum_address
            return self.known_nodes(nodes_dict=ursula.known_nodes.abridged_nodes_dict(),
                                    registry=ursula.registry,
                                    teacher_checksum=teacher_checksum)
