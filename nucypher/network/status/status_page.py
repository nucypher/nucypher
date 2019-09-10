import os
from datetime import datetime, timedelta
from os.path import dirname, abspath
from string import Template

import dash_core_components as dcc
import dash_html_components as html
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from dash import Dash
from dash.dependencies import Output, Input
from flask import Flask
from maya import MayaDT
from twisted.logger import Logger

import nucypher
from nucypher.blockchain.eth.token import NU
from nucypher.characters.base import Character
from nucypher.network.nodes import Learner


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
    def header() -> html.Div:
        return html.Div([html.Div(f'v{nucypher.__version__}', id='version')],
                        className="logo-widget")

    def previous_states(self, learner: Learner) -> html.Div:
        states_dict = learner.known_nodes.abridged_states_dict()
        return html.Div([
                html.H4('Previous States'),
                html.Div([
                    self.states_table(states_dict)
                ]),
            ], className='row')

    def states_table(self, states_dict) -> html.Table:
        previous_states = list(states_dict.values())[:3]   # only latest 3
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

    def known_nodes(self, learner: Learner) -> html.Div:
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
            html.Div([self.nodes_table(nodes, teacher_index)], className='row')
        ], className='row')

    def nodes_table(self, nodes, teacher_index) -> html.Table:
        rows = []
        for index, node_info in enumerate(nodes):
            row = []
            for col in self.COLUMNS:
                components = self.generate_components(node_info=node_info)
                cell = components[col]
                if cell:
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
    def generate_components(node_info: dict):
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

        etherscan_url = f'https://goerli.etherscan.io/address/{node_info["checksum_address"]}'
        components = {
            'Icon': icon,
            'Checksum': html.Td(html.A(f'{node_info["checksum_address"][:10]}...',
                                       href=etherscan_url,
                                       target='_blank')),
            'Nickname': nickname,
            'Timestamp': html.Td(node_info['timestamp']),
            'Last Seen': html.Td(node_info['last_seen']),
            'Fleet State': fleet_state
        }

        return components


class MoeStatusPage(NetworkStatusPage):
    """
    Status application for 'Moe' monitoring node.
    """

    def __init__(self, moe, ws_port: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws_port = ws_port

        # updates can be directly provided included in javascript snippet
        # TODO: Configurable template path
        template_path = os.path.join(abspath(dirname(__file__)), 'moe.html')
        with open(template_path, 'r') as file:
            moe_template = file.read()
            self.dash_app.index_string = Template(moe_template).substitute(ws_port=ws_port)

        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),

            # Update buttons also used for hendrix WS topic notifications
            html.Div([
                html.Img(src='/assets/nucypher_logo.png', className='banner'),
                html.Button("Refresh States", id='hidden-state-button', type='submit'),
                html.Button("Refresh Known Nodes", id='hidden-node-button', type='submit'),
            ], id="controls"),

            ###############################################################

            html.Div([
                html.Div([
                    html.Div(id='header'),
                    html.Div(id='current-period'),
                    html.Div(id='time-remaining'),
                    html.Div(id='domains'),
                    html.Div(id='prev-states'),
                    html.Div(id='active-stakers'),
                    html.Div(id='registry-uri'),
                    html.Div(id='staked-tokens'),
                ], id='widgets'),

                html.Div(id='known-nodes'),
            ], id='main'),

            dcc.Interval(
                id='interval-component',
                interval=15 * 1000,
                n_intervals=0
            ),
        ])

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header()

        @self.dash_app.callback(Output('prev-states', 'children'),
                                [Input('url', 'pathname')])
        def state(pathname):
            return self.previous_states(moe)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def known_nodes(n):
            return self.known_nodes(moe)

        @self.dash_app.callback(Output('active-stakers', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def active_stakers(n):
            return html.Div([html.H4("Active Stakers"),
                             html.H5(f"{len(moe.known_nodes)} nodes")])

        @self.dash_app.callback(Output('current-period', 'children'),
                                [Input('url', 'pathname')])
        def current_period(pathname):
            return html.Div([html.H4("Current Period"),
                             html.H5(moe.staking_agent.get_current_period())])

        @self.dash_app.callback(Output('time-remaining', 'children'),
                                [Input('interval-component', 'n_intervals')])
        def time_remaining(n):
            tomorrow = datetime.now() + timedelta(1)
            midnight = datetime(year=tomorrow.year, month=tomorrow.month,
                                day=tomorrow.day, hour=0, minute=0, second=0)
            seconds_remaining = MayaDT.from_datetime(midnight).slang_time()
            return html.Div([html.H4("Next Period"),
                             html.H5(seconds_remaining)])

        @self.dash_app.callback(Output('domains', 'children'), [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = ' | '.join(moe.learning_domains)
            return html.Div([
                html.H4('Learning Domains'),
                html.H5(domains),
            ])

        @self.dash_app.callback(Output('staked-tokens', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def staked_tokens(pathname):
            nu = NU.from_nunits(moe.staking_agent.get_global_locked_tokens())
            return html.Div([
                html.H4('Staked Tokens'),
                html.H5(f"{nu}"),
            ])

        @self.dash_app.callback(Output('registry-uri', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def contract_status(pathname):
            uri = moe.registry.id[:16]
            return html.Div([
                html.H4('Registry Checksum'),
                html.H5(f"{uri}"),
                html.A(f'{moe.token_agent.contract_name} - {moe.token_agent.contract_address}',
                       href=f'https://goerli.etherscan.io/address/{moe.token_agent.contract_address}',
                       target='_blank'),
                html.A(f'{moe.staking_agent.contract_name} - {moe.staking_agent.contract_address}',
                       href=f'https://goerli.etherscan.io/address/{moe.staking_agent.contract_address}',
                       target='_blank'),
                html.A(f'{moe.policy_agent.contract_name} - {moe.policy_agent.contract_address}',
                       href=f'https://goerli.etherscan.io/address/{moe.policy_agent.contract_address}',
                       target='_blank'),
                html.A(f'{moe.adjudicator_agent.contract_name} - {moe.adjudicator_agent.contract_address}',
                       href=f'https://goerli.etherscan.io/address/{moe.adjudicator_agent.contract_address}',
                       target='_blank'),
            ], className='stacked-widget')


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
            html.Div(id='domains'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            # use a periodic update interval (every 2s) instead of notification updates from hendrix used by Moe
            dcc.Interval(id='status-update', interval=2000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'), [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header()

        @self.dash_app.callback(Output('domains', 'children'), [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = ''
            for domain in ursula.learning_domains:
                domains += f' | {domain} '
            return html.Div([
                html.H4('Domains', className='one column'),
                html.H5(domains, className='eleven columns'),
            ], className='row')

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

        @self.dash_app.callback(Output('prev-states', 'children'), [Input('status-update', 'n_intervals')])
        def state(n):
            """Simply update periodically"""
            return self.previous_states(ursula)

        @self.dash_app.callback(Output('known-nodes', 'children'), [Input('status-update', 'n_intervals')])
        def known_nodes(n):
            """Simply update periodically"""
            return self.known_nodes(ursula)
