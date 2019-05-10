import os

import dash_core_components as dcc
import dash_dangerously_set_inner_html
import dash_html_components as html
from dash import Dash
from dash.dependencies import Output, Input, Event
from flask import Flask
from twisted.logger import Logger

import nucypher
from nucypher.characters.base import Character
from nucypher.network.nodes import Learner


class NetworkStatusPage:
    COLUMNS = ['Icon', 'Checksum', 'Nickname', 'Timestamp', 'Last Seen', 'Fleet State']

    def __init__(self,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 *args,
                 **kwargs) -> None:
        self.log = Logger(self.__class__.__name__)

        self.dash_app = Dash(name=__name__,
                             server=flask_server,
                             assets_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets'),
                             url_base_pathname=route_url,
                             suppress_callback_exceptions=True)
        self.dash_app.title = title

    @staticmethod
    def header(title) -> html.Div:
        return html.Div([
            html.Div([
                html.Div([
                    html.Img(src='/assets/nucypher_logo.png'),
                ], className='banner'),
                html.Div([
                    html.H1(title, id='status-title', className='app_name'),
                ], className='row'),
                html.Div(f'v{nucypher.__version__}', className='row')
            ]),
        ])

    @staticmethod
    def previous_states(learner: Learner) -> html.Div:
        states_dict = learner.known_nodes.abridged_states_dict()
        return html.Div([
            html.H2('Previous States'),
            html.Div([
                NetworkStatusPage.states_table(states_dict)
            ]),
        ], className='row')

    @staticmethod
    def states_table(states_dict) -> html.Table:
        previous_states = list(states_dict.values())[:5]   # only latest 5
        row = []
        for state in previous_states:
            # store previous states in reverse order
            row.insert(0, html.Td(NetworkStatusPage.state_detail(state)))
        return html.Table([html.Tr(row, id='state-table', className='row')])

    @staticmethod
    def state_detail(state) -> html.Div:
        return html.Div([
            html.H5(state['nickname']),
            html.Div([
                html.Div(state['symbol'], className='single-symbol'),
                html.Span(state['updated'], className='small'),
            ], className='nucypher-nickname-icon', style={'border-color': state["color_hex"]})
        ], className='state')

    @staticmethod
    def known_nodes(learner: Learner, title='Network Nodes') -> html.Div:
        nodes = list()

        nodes_dict = learner.known_nodes.abridged_nodes_dict()
        teacher_node = learner.current_teacher_node()
        teacher_index = None
        for checksum in nodes_dict:
            node_data = nodes_dict[checksum]
            if checksum == teacher_node.checksum_public_address:
                teacher_index = len(nodes)

            nodes.append(node_data)

        return html.Div([
            html.H2(title),
            html.Div([
                html.Div('* Current Teacher',
                         style={'backgroundColor': '#1E65F3', 'color': 'white'},
                         className='two columns'),
            ], className='row'),
            html.Br(),
            html.Div([
                NetworkStatusPage.nodes_table(nodes, teacher_index)
            ], className='row')
        ], className='row')

    @staticmethod
    def nodes_table(nodes, teacher_index) -> html.Table:
        rows = []

        for i in range(len(nodes)):
            row = []
            node_dict = nodes[i]
            for col in NetworkStatusPage.COLUMNS:
                # update this depending on which
                # columns you want to show links for
                # and what you want those links to be
                cell = None
                if col == 'Icon':
                    icon_details = node_dict['icon_details']
                    cell = html.Td(children=html.Div([
                        html.Span(f'{icon_details["first_symbol"]}',
                                  className='single-symbol',
                                  style={'color': icon_details['first_color']}),
                        html.Span(f'{icon_details["second_symbol"]}',
                                  className='single-symbol',
                                  style={'color': icon_details['second_color']})
                    ], className='symbols'))
                elif col == 'Checksum':
                    cell = html.Td(f'{node_dict["checksum_address"][:10]}...')
                elif col == 'Nickname':
                    cell = html.Td(html.A(node_dict['nickname'],
                                          href='https://{}/status'.format(node_dict['rest_url']),
                                          target='_blank'))
                elif col == 'Timestamp':
                    cell = html.Td(node_dict['timestamp'])
                elif col == 'Last Seen':
                    cell = html.Td(node_dict['last_seen'])
                elif col == 'Fleet State':
                    # render html value directly
                    cell = html.Td(children=html.Div([
                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(node_dict['fleet_state_icon'])
                    ]))

                if cell is not None:
                    row.append(cell)

            style_dict = {'overflowY': 'scroll'}
            if i == teacher_index:
                # highlight teacher
                style_dict['backgroundColor'] = '#1E65F3'
                style_dict['color'] = 'white'

            rows.append(html.Tr(row, style=style_dict, className='row'))
        return html.Table(
            # header
            [html.Tr([html.Th(col) for col in NetworkStatusPage.COLUMNS], className='row')] +
            rows,
            id='node-table')


class MoeStatusPage(NetworkStatusPage):
    """
    Status application for 'Moe' monitoring node.
    """

    def __init__(self,
                 moe: Learner,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 ws_port: int,
                 *args,
                 **kwargs) -> None:
        NetworkStatusPage.__init__(self, title, flask_server, route_url, args, kwargs)

        # modify index_string page template so that the websocket port for hendrix
        # updates can be directly provided included in javascript snippet
        self.dash_app.index_string = '''
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>{%title%}</title>
                {%favicon%}
                {%css%}
            </head>
            <body>
                {%app_entry%}
                
                <script>
                    window.onload = function () {
                        const ws_port = "''' + str(ws_port) + '''";
                        const origin_hostname = window.location.hostname;
                        const socket = new WebSocket("ws://"+ origin_hostname + ":" + ws_port);
                        socket.binaryType = "arraybuffer";
                                    
                        socket.onopen = function () {
                            socket.send(JSON.stringify({'hx_subscribe': 'states'}));
                            socket.send(JSON.stringify({'hx_subscribe': 'nodes'}));
                            isopen = true;
                        }
                        
                        socket.addEventListener('message', function (event) {
                            console.log("Message from server ", event.data);
                            if (event.data.startsWith("[\\"states\\"")) {
                                var hidden_state_button = document.getElementById("hidden-state-button");
                                // weird timing issue with onload and DOM element potentially not being created as yet
                                if( hidden_state_button != null ) {
                                    hidden_state_button.click(); // Update states
                                }
                            } else if (event.data.startsWith("[\\"nodes\\"")) {
                                var hidden_node_button = document.getElementById("hidden-node-button");
                                // weird timing issue with onload and DOM element potentially not being created as yet
                                if( hidden_node_button != null ) {
                                    hidden_node_button.click(); // Update nodes
                                }
                            }
                        });
                        
                        socket.onerror = function (error) {
                            console.log(error.data);
                        }
                    }
                </script>
                <footer>
                    {%config%}
                    {%scripts%}
                </footer>
            </body>
        </html>
        '''

        self.dash_app.layout = html.Div([
            # hidden update buttons for hendrix notifications
            html.Div([
                html.Button(id='hidden-state-button', type='submit', hidden=True),
                html.Button(id='hidden-node-button', type='submit', hidden=True),
            ], hidden=True),

            dcc.Location(id='url', refresh=False),
            html.Div(id='header'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
        ])

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return NetworkStatusPage.header(title)

        @self.dash_app.callback(Output('prev-states', 'children'),
                                [Input('url', 'pathname')],  # on page-load
                                events=[Event('hidden-state-button', 'click')])  # when notified by websocket message
        def state(pathname):
            return NetworkStatusPage.previous_states(moe)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                [Input('url', 'pathname')],  # on page-load
                                events=[Event('hidden-node-button', 'click')])  # when notified by websocket message
        def known_nodes(pathname):
            return NetworkStatusPage.known_nodes(moe)


class UrsulaStatusPage(NetworkStatusPage):
    """
    Status application for Ursula node.
    """

    def __init__(self,
                 ursula: Character,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 *args,
                 **kwargs) -> None:
        NetworkStatusPage.__init__(self, title, flask_server, route_url, args, kwargs)

        self.dash_app.assets_ignore = 'hendrix-update.js'  # javascript not needed for Ursula
        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='header'),
            html.Div(id='ursula_info'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            # use a periodic update interval (every 2s) instead of notification updates from hendrix used by Moe
            dcc.Interval(id='status-update', interval=2000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return NetworkStatusPage.header(title)

        @self.dash_app.callback(Output('ursula_info', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def ursula_info(pathname):
            domains = ''
            for domain in ursula.learning_domains:
                domains += f'  {domain.decode("utf-8")}  '

            return html.Div([
                html.Div([
                    html.H4('Icon', className='one column'),
                    html.Div([
                        html.Span(f'{ursula.nickname_metadata[0][1]}', className='single-symbol'),
                        html.Span(f'{ursula.nickname_metadata[1][1]}', className='single-symbol'),
                    ], className='symbols three columns'),

                ], className='row'),
                html.Div([
                    html.H4('Domains', className='one column'),
                    html.H4(domains, className='eleven columns'),
                ], className='row')
            ], className='row')

        @self.dash_app.callback(Output('prev-states', 'children'),
                                events=[Event('status-update', 'interval')])  # simply update periodically
        def state():
            return NetworkStatusPage.previous_states(ursula)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                events=[Event('status-update', 'interval')])  # simply update periodically
        def known_nodes():
            return NetworkStatusPage.known_nodes(ursula, title='Peers')
