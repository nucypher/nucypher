import os
from os.path import dirname, abspath

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
from constant_sorrow.constants import UNKNOWN_FLEET_STATE


class NetworkStatusPage:
    COLUMNS = ['Icon', 'Checksum', 'Nickname', 'Timestamp', 'Last Seen', 'Fleet State']

    def __init__(self, title: str, flask_server: Flask, route_url: str):
        self.log = Logger(self.__class__.__name__)
        self.assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
        self.dash_app = Dash(name=__name__,
                             server=flask_server,
                             assets_folder=self.assets_path,
                             url_base_pathname=route_url,
                             suppress_callback_exceptions=False)  # TODO: Set to True by default or make configurable
        self.dash_app.title = title

    @property
    def title(self) -> str:
        return self.dash_app.title

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

    def previous_states(self, learner: Learner) -> html.Div:
        domains = learner.learning_domains
        states_dict = learner.known_nodes.abridged_states_dict()
        return html.Div([
            html.Div([
                html.H2('Domains'),
                html.Div(f'{", ".join(domains)}')
            ], className='row'),
            html.Div([
                html.H2('Previous States'),
                html.Div([
                    self.states_table(states_dict)
                ]),
            ], className='row')
        ])

    def states_table(self, states_dict) -> html.Table:
        previous_states = list(states_dict.values())[:5]   # only latest 5
        row = []
        for state in previous_states:
            # store previous states in reverse order
            row.insert(0, html.Td(self.state_detail(state)))
        return html.Table([html.Tr(row, id='state-table', className='row')])

    @staticmethod
    def state_detail(state) -> html.Div:
        return html.Div([
            html.Span(state['nickname']),
            html.Div([
                html.Div(state['symbol'], className='single-symbol'),
                html.Span(state['updated'], className='small'),
            ], className='nucypher-nickname-icon', style={'border-color': state["color_hex"]})
        ], className='state')

    def known_nodes(self, learner: Learner, title='Network Nodes') -> html.Div:
        nodes = list()
        nodes_dict = learner.known_nodes.abridged_nodes_dict()
        teacher_node = learner.current_teacher_node()
        teacher_index = None
        for checksum in nodes_dict:
            node_data = nodes_dict[checksum]
            if checksum == teacher_node.checksum_address:
                teacher_index = len(nodes)
            nodes.append(node_data)

        return html.Div([
            html.H2(title),
            html.Div([self.nodes_table(nodes, teacher_index)], className='row')
        ], className='row')

    def nodes_table(self, nodes, teacher_index) -> html.Table:
        rows = []
        for index, node_info in enumerate(nodes):
            row = []
            for col in self.COLUMNS:
                cell = self.generate_cell(column_name=col, node_info=node_info)
                if cell is not None:
                    row.append(cell)

            style_dict = {'overflowY': 'scroll'}
            # highlight teacher
            if index == teacher_index:
                style_dict['backgroundColor'] = '#1E65F3'
                style_dict['color'] = 'white'

            rows.append(html.Tr(row, style=style_dict, className='row'))

        table = html.Table(
            # header
            [html.Tr([html.Th(col) for col in self.COLUMNS], className='row')] +
            rows,
            id='node-table'
        )
        return table

    @staticmethod
    def generate_cell(column_name: str, node_info: dict):
        """
        Update this depending on which columns you want to show links for
        and what you want those links to be.
        """
        icon = html.Td(children=html.Div([html.Span(f'{node_info["icon_details"]["first_symbol"]}',
                                                    className='single-symbol',
                                                    style={'color': node_info["icon_details"]['first_color']}),
                                          html.Span(f'{node_info["icon_details"]["second_symbol"]}',
                                                    className='single-symbol',
                                                    style={'color': node_info["icon_details"]['second_color']})],
                                         className='symbols'))

        nickname = html.Td(html.A(node_info['nickname'],
                                  href=f'https://{node_info["rest_url"]}/status',
                                  target='_blank'))

        # Fleet State
        fleet_state_div = []
        fleet_state_icon = node_info['fleet_state_icon']
        if fleet_state_icon is not UNKNOWN_FLEET_STATE:
            icon_list = node_info['fleet_state_icon']
            fleet_state_div = icon_list
        fleet_state = html.Td(children=html.Div(fleet_state_div))

        components = {
            'Icon': icon,
            'Checksum': html.Td(f'{node_info["checksum_address"][:10]}...'),
            'Nickname': nickname,
            'Timestamp': html.Td(node_info['timestamp']),
            'Last Seen': html.Td(node_info['last_seen']),
            'Fleet State': fleet_state
        }

        cell = components[column_name]
        return cell


class MoeStatusPage(NetworkStatusPage):
    """
    Status application for 'Moe' monitoring node.
    """

    def __init__(self, moe: Learner, ws_port: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws_port = ws_port

        # modify index_string page template so that the websocket port for hendrix
        # updates can be directly provided included in javascript snippet
        template_path = os.path.join(abspath(dirname(__file__)), 'moe.html')
        with open(template_path, 'r') as file:
            self.dash_app.index_string = file.read()

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

        @self.dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header(self.title)

        @self.dash_app.callback(Output('prev-states', 'children'),
                                [Input('url', 'pathname')],  # on page-load
                                events=[Event('hidden-state-button', 'click')])  # when notified by websocket message
        def state(pathname):
            return self.previous_states(moe)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                [Input('url', 'pathname')],  # on page-load
                                events=[Event('hidden-node-button', 'click')])  # when notified by websocket message
        def known_nodes(pathname):
            return self.known_nodes(moe)


class UrsulaStatusPage(NetworkStatusPage):
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
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            # use a periodic update interval (every 2s) instead of notification updates from hendrix used by Moe
            dcc.Interval(id='status-update', interval=2000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header(self.title)

        @self.dash_app.callback(Output('ursula_info', 'children'), [Input('url', 'pathname')])  # on page-load
        def ursula_info(pathname):
            domains = ''
            for domain in ursula.learning_domains:
                domains += f' | {domain} '
            info = html.Div([
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
            return info

        @self.dash_app.callback(Output('prev-states', 'children'), events=[Event('status-update', 'interval')])
        def state():
            """Simply update periodically"""
            return self.previous_states(ursula)

        @self.dash_app.callback(Output('known-nodes', 'children'), events=[Event('status-update', 'interval')])
        def known_nodes():
            """Simply update periodically"""
            return self.known_nodes(ursula, title='Peers')
