import os

import dash_daq as daq
import dash_html_components as html
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from cryptography.hazmat.primitives.asymmetric import ec
from dash import Dash
from flask import Flask
from maya import MayaDT
from pendulum.parsing import ParserError
from twisted.logger import Logger

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.characters.base import Character
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.nodes import Learner, FleetStateTracker
from nucypher.network.server import TLSHostingPower


class NetworkStatusPage:
    NODE_TABLE_COLUMNS = ['Status', 'Checksum', 'Nickname', 'Timestamp', 'Last Seen', 'Fleet State']

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
        return html.Div([html.Div(f'v{nucypher.__version__}', id='version')], className="logo-widget")

    def previous_states(self, learner: Learner) -> html.Div:
        previous_states = list(reversed(learner.known_nodes.states.values()))[:5]  # only latest 5
        return html.Div([
                html.H4('Previous States'),
                html.Div([
                    self._states_table(previous_states)
                ]),
            ], className='row')

    def _states_table(self, states) -> html.Table:
        row = []
        for state in states:
            # add previous states in order (already reversed)
            row.append(html.Td(self.state_detail(FleetStateTracker.abridged_state_details(state))))
        return html.Table([html.Tr(row, id='state-table')])

    @staticmethod
    def state_detail(state_detail_dict) -> html.Div:
        return html.Div([
            html.Div([
                html.Div(state_detail_dict['symbol'], className='single-symbol'),
            ], className='nucypher-nickname-icon', style={'border-color': state_detail_dict['color_hex']}),
            html.Span(state_detail_dict['nickname']),
            html.Span(state_detail_dict['updated'], className='small'),
        ], className='state', style={'background-color': state_detail_dict['color_hex']})

    def known_nodes(self, nodes_dict: dict, registry, teacher_checksum: str = None) -> html.Div:
        nodes = list()
        teacher_index = None
        for checksum in nodes_dict:
            node_data = nodes_dict[checksum]
            if node_data:
                if checksum == teacher_checksum:
                    teacher_index = len(nodes)
                nodes.append(node_data)

        return html.Div([
            html.H4('Network Nodes'),
            html.Div([
                html.Div('* Current Teacher',
                         style={'backgroundColor': '#1E65F3', 'color': 'white'},
                         className='two columns'),
            ]),
            html.Div([self.nodes_table(nodes, teacher_index, registry)])
        ])

    def nodes_table(self, nodes, teacher_index, registry) -> html.Table:
        rows = []
        for index, node_info in enumerate(nodes):
            row = []
            # TODO: could return list (skip column for-loop); however, dict is good in case of re-ordering of columns
            components = NetworkStatusPage.generate_node_table_components(node_info=node_info, registry=registry)
            for col in self.NODE_TABLE_COLUMNS:
                cell = components[col]
                if cell:
                    row.append(cell)

            style_dict = {'overflowY': 'scroll'}
            # highlight teacher
            if index == teacher_index:
                style_dict['backgroundColor'] = '#1E65F3'
                style_dict['color'] = 'white'

            rows.append(html.Tr(row, style=style_dict, className='node-row'))

        table = html.Table(
            # header
            [html.Tr([html.Th(col) for col in self.NODE_TABLE_COLUMNS], className='table-header')] +
            rows,
            id='node-table'
        )
        return table

    @staticmethod
    def generate_node_table_components(node_info: dict, registry):
        """
        Update this depending on which columns you want to show links for
        and what you want those links to be.
        """
        identity = html.Td(children=html.Div([
            html.A(node_info['nickname'],
                   href=f'https://{node_info["rest_url"]}/status',
                   target='_blank')
        ]))

        # Fleet State
        fleet_state_div = []
        fleet_state_icon = node_info['fleet_state_icon']
        if fleet_state_icon is not UNKNOWN_FLEET_STATE:
            icon_list = node_info['fleet_state_icon']
            fleet_state_div = icon_list
        fleet_state = html.Td(children=html.Div(fleet_state_div))

        staker_address = node_info['staker_address']

        # Blockchainy (TODO)
        agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        current_period = agent.get_current_period()
        last_confirmed_period = agent.get_last_active_period(staker_address)
        status = NetworkStatusPage.get_node_status(agent, staker_address, current_period, last_confirmed_period)

        etherscan_url = f'https://goerli.etherscan.io/address/{node_info["staker_address"]}'
        try:
            slang_last_seen = MayaDT.from_rfc3339(node_info['last_seen']).slang_time()
        except ParserError:
            slang_last_seen = node_info['last_seen']

        components = {
            'Status': status,
            'Checksum': html.Td(html.A(f'{node_info["staker_address"][:10]}...',
                                       href=etherscan_url,
                                       target='_blank')),
            'Nickname': identity,
            'Timestamp': html.Td(node_info['timestamp']),
            'Last Seen': html.Td([slang_last_seen, f" | Period {last_confirmed_period}"]),
            'Fleet State': fleet_state
        }

        return components

    @staticmethod
    def get_node_status(agent, staker_address, current_period, last_confirmed_period):
        missing_confirmations = current_period - last_confirmed_period
        worker = agent.get_worker_from_staker(staker_address)
        if worker == BlockchainInterface.NULL_ADDRESS:
            missing_confirmations = BlockchainInterface.NULL_ADDRESS

        color_codex = {-1: ('green', 'OK'),  # Confirmed Next Period
                       0: ('#e0b32d', 'Pending'),  # Pending Confirmation of Next Period
                       current_period: ('#525ae3', 'Idle'),  # Never confirmed
                       BlockchainInterface.NULL_ADDRESS: ('red', 'Headless')  # Headless Staker (No Worker)
                       }
        try:
            color, status_message = color_codex[missing_confirmations]
        except KeyError:
            color, status_message = 'red', f'{missing_confirmations} Unconfirmed'
        status_cell = daq.Indicator(id='Status',
                                    color=color,
                                    value=True,
                                    label=status_message,
                                    labelPosition='right',
                                    size=25)  # pixels
        status = html.Td(status_cell)
        return status
