import os
from datetime import datetime, timedelta
from os.path import dirname, abspath
from string import Template

import dash_core_components as dcc
import dash_daq as daq
import dash_html_components as html
import plotly.graph_objs as go
from constant_sorrow.constants import UNKNOWN_FLEET_STATE
from dash import Dash
from dash.dependencies import Output, Input
from flask import Flask
from maya import MayaDT
from twisted.logger import Logger

import nucypher
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.characters.base import Character
from nucypher.network.nodes import Learner


class NetworkStatusPage:
    NODE_TABLE_COLUMNS = ['Status', 'Icon', 'Checksum', 'Nickname', 'Timestamp', 'Last Seen', 'Fleet State']

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
            html.Div([
                html.Div(className='dot', style={'background-color': state['color_hex']}),
                html.Div(state['symbol'], className='single-symbol'),
            ], className='nucypher-nickname-icon', style={'border-color': state['color_hex']}),
            html.Span(state['nickname']),
            html.Span(state['updated'], className='small'),
        ], className='state')

    def known_nodes(self, character: Character) -> html.Div:
        nodes = list()
        nodes_dict = character.known_nodes.abridged_nodes_dict()
        teacher_node = character.current_teacher_node()
        teacher_index = None
        for checksum in nodes_dict:
            node_data = nodes_dict[checksum]
            if checksum == teacher_node.checksum_address:
                teacher_index = len(nodes)
            nodes.append(node_data)

        return html.Div([
            html.H4('Network Nodes'),
            html.Div([
                html.Div('* Current Teacher',
                         style={'backgroundColor': '#1E65F3', 'color': 'white'},
                         className='two columns'),
            ], className='row'),
            html.Div([self.nodes_table(nodes, teacher_index, character.registry)],
                     className='row')
        ], className='row')

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

            rows.append(html.Tr(row, style=style_dict, className='row'))

        table = html.Table(
            # header
            [html.Tr([html.Th(col) for col in self.NODE_TABLE_COLUMNS], className='row')] +
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

        staker_address = node_info['staker_address']
        agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        current_period = agent.get_current_period()
        last_confirmed_period = agent.get_last_active_period(staker_address)
        status = NetworkStatusPage.get_node_status(agent, staker_address, current_period, last_confirmed_period)

        etherscan_url = f'https://goerli.etherscan.io/address/{node_info["checksum_address"]}'
        components = {
            'Status': status,
            'Icon': icon,
            'Checksum': html.Td(html.A(f'{node_info["checksum_address"][:10]}...',
                                       href=etherscan_url,
                                       target='_blank')),
            'Nickname': nickname,
            'Timestamp': html.Td(node_info['timestamp']),
            'Last Seen': html.Td([node_info['last_seen'], f" | Period {last_confirmed_period}"]),
            'Fleet State': fleet_state
        }

        return components

    @staticmethod
    def get_node_status(agent, staker_address, current_period, last_confirmed_period):
        missing_confirmations = current_period - last_confirmed_period
        worker = agent.get_worker_from_staker(staker_address)
        if worker == BlockchainInterface.NULL_ADDRESS:
            missing_confirmations = BlockchainInterface.NULL_ADDRESS

        color_codex = {-1: ('green', ' '),  # Confirmed Next Period
                       0: ('#e0b32d', 'Pending'),  # Pending Confirmation of Next Period
                       current_period: ('#525ae3', 'Idle'),  # Never confirmed
                       BlockchainInterface.NULL_ADDRESS: ('red', 'Headless')  # Headless Staker (No Worker)
                       }
        try:
            color, status_message = color_codex[missing_confirmations]
        except KeyError:
            color, status_message = 'red', f'{missing_confirmations} Unconfirmed'
        status_cell = daq.Indicator(id='Status', color=color, value=True,
                                    label=status_message, labelPosition='bottom', size=10)
        status = html.Td(status_cell)
        return status


class MoeStatusPage(NetworkStatusPage):
    """
    Status application for 'Moe' monitoring node.
    """

    def __init__(self, moe, ws_port: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws_port = ws_port
        self.moe = moe

        from nucypher.network.status.utility.moe_crawler import MoeBlockchainCrawler
        self.moe_crawler = MoeBlockchainCrawler(moe=moe)
        self.moe_crawler.start()

        self.moe_db_client = self.moe_crawler.get_db_client()

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
                html.Div(id='header'),
                html.Button("Refresh States", id='hidden-state-button', type='submit'),
                html.Button("Refresh Known Nodes", id='hidden-node-button', type='submit'),
            ], id="controls"),

            ###############################################################

            html.Div([
                html.Div([
                    html.Div(id='current-period'),
                    html.Div(id='time-remaining'),
                    html.Div(id='domains'),
                    html.Div(id='active-stakers'),
                    html.Div(id='registry-uri'),
                    html.Div(id='staked-tokens'),
                    html.Div(id='prev-num-stakers-graph'),
                    html.Div(id='prev-locked-stake-graph'),
                    # html.Div(id='locked-stake-graph'),
                    # html.Div(id='schedule'),
                ], id='widgets'),

                html.Div([
                    html.Div(id='prev-states'),
                    html.Br(),
                    html.Div(id='known-nodes'),
                ]),

            ], id='main'),

            dcc.Interval(
                id='interval-component',
                interval=30 * 1000,
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
                                [Input('url', 'pathname')])
        def known_nodes(n):
            return self.known_nodes(moe)

        @self.dash_app.callback(Output('active-stakers', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def active_stakers(n):
            staker_addresses = moe.staking_agent.get_stakers()
            return html.Div([html.H4("Active Ursulas"),
                             html.H5(f"{len(moe.known_nodes)}/{len(staker_addresses)}")])

        @self.dash_app.callback(Output('current-period', 'children'),
                                [Input('url', 'pathname')])
        def current_period(pathname):
            return html.Div([html.H4("Current Period"),
                             html.H5(moe.staking_agent.get_current_period())])

        @self.dash_app.callback(Output('time-remaining', 'children'),
                                [Input('interval-component', 'n_intervals')])
        def time_remaining(n):
            tomorrow = datetime.utcnow() + timedelta(days=1)
            midnight = datetime(year=tomorrow.year, month=tomorrow.month,
                                day=tomorrow.day, hour=0, minute=0, second=0, microsecond=0)
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

        @self.dash_app.callback(Output('prev-locked-stake-graph', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def prev_locked_tokens(pathname):
            prior_periods = 30
            locked_tokens_dict = self.moe_db_client.get_historical_locked_tokens_over_range(prior_periods)
            fig = go.Figure(data=[
                                go.Bar(
                                    textposition='auto',
                                    x=list(locked_tokens_dict.keys()),
                                    y=list(locked_tokens_dict.values()),
                                    name='Locked Stake',
                                    marker=go.bar.Marker(color='rgb(30, 101, 243)')
                                )
                            ],
                            layout=go.Layout(
                                title=f'Staked NU over the previous {prior_periods} days.',
                                xaxis={
                                    'title': 'Date',
                                    'nticks': len(locked_tokens_dict),
                                },
                                yaxis={
                                    'title': 'NU Tokens',
                                    'zeroline': False,
                                },
                                showlegend=False,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            ))

            return dcc.Graph(figure=fig, id='prev-locked-graph')

        @self.dash_app.callback(Output('prev-num-stakers-graph', 'children'),
                                [Input('hidden-node-button', 'n_clicks')])
        def prev_locked_tokens(pathname):
            prior_periods = 30
            num_stakers_dict = self.moe_db_client.get_historical_num_stakers_over_range(prior_periods)
            fig = go.Figure(data=[
                                go.Scatter(
                                    mode='lines+markers',
                                    x=list(num_stakers_dict.keys()),
                                    y=list(num_stakers_dict.values()),
                                    name='Num Stakers',
                                    marker={'color': 'rgb(30, 101, 243)'}
                                )
                            ],
                            layout=go.Layout(
                                title=f'Num Stakers over the previous {prior_periods} days.',
                                xaxis={
                                    'title': 'Date',
                                    'nticks': len(num_stakers_dict)
                                },
                                yaxis={
                                    'title': 'Stakers',
                                    'zeroline': False,
                                },
                                showlegend=False,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            ))

            return dcc.Graph(figure=fig, id='prev-stakers-graph')

        # @self.dash_app.callback(Output('locked-stake-graph', 'children'),
        #                         [Input('hidden-node-button', 'n_clicks')])
        # def future_locked_tokens(pathname):
        #     periods = 30
        #     token_counter = self.moe_db_client.get_future_locked_tokens_over_day_range(periods)
        #     period_range = list(range(1, periods + 1))
        #     fig = go.Figure(data=[
        #                         go.Bar(
        #                             textposition='auto',
        #                             x=period_range,
        #                             y=list(token_counter.values()),
        #                             name='Stake',
        #                             marker=go.bar.Marker(color='rgb(30, 101, 243)')
        #                         )
        #                     ],
        #                     layout=go.Layout(
        #                         title=f'Staked NU over the next {periods} days.',
        #                         xaxis={'title': 'Days'},
        #                         yaxis={'title': 'NU Tokens'},
        #                         showlegend=False,
        #                         legend=go.layout.Legend(x=0, y=1.0),
        #                         paper_bgcolor='rgba(0,0,0,0)',
        #                         plot_bgcolor='rgba(0,0,0,0)'
        #                     ))
        #
        #     config = {"displaylogo": False,
        #               'autosizable': True,
        #               'responsive': True,
        #               'fillFrame': False,
        #               'displayModeBar': False}
        #     return dcc.Graph(figure=fig, id='locked-graph', config=config)

        # @self.dash_app.callback(Output('schedule', 'children'), [Input('url', 'pathname')])
        # def schedule(pathname):
        #
        #     current_period = moe.staking_agent.get_current_period()
        #     staker_addresses = moe.staking_agent.get_stakers()
        #
        #     df = []
        #     for index, address in enumerate(staker_addresses):
        #         stakes = StakeList(checksum_address=address, registry=moe.registry)
        #         stakes.refresh()
        #         end = stakes.terminal_period
        #         delta = end - current_period
        #
        #         economics = TokenEconomicsFactory.get_economics(registry=moe.registry)
        #         start_date = datetime_at_period(current_period, seconds_per_period=economics.seconds_per_period)
        #         end_date = datetime_at_period(stakes.terminal_period, seconds_per_period=economics.seconds_per_period)
        #         stake = moe.staking_agent.get_locked_tokens(staker_address=address, periods=delta)
        #         nu_stake = float(NU.from_nunits(stake).to_tokens())
        #
        #         row = dict(Task=address[:10],
        #                    Start=str(start_date.date),
        #                    Finish=str(end_date.date),
        #                    Stake=nu_stake)
        #         df.append(row)
        #
        #     # Normalize, Scale and Mutate
        #     total = sum(row['Stake'] for row in df)
        #     for row in df:
        #         row['Stake'] = (row['Stake'] // total) * 100
        #
        #     color_scale = ['rgb(31, 141, 143)', 'rgb(31, 243, 243)']
        #     fig = ff.create_gantt(df,
        #                           colors=color_scale,
        #                           index_col='Stake',
        #                           title="Ursula Fleet Staking Schedule",
        #                           bar_width=0.3,
        #                           showgrid_x=True,
        #                           showgrid_y=True)
        #
        #     fig['layout'].update(autosize=True,
        #                          width=None,
        #                          height=None)
        #
        #     config = {"displaylogo": False,
        #               'autosizable': True,
        #               'responsive': True,
        #               'fillFrame': False,
        #               'displayModeBar': False}
        #
        #     schedule_graph = dcc.Graph(figure=fig, id='llamas-graph', config=config)
        #     return schedule_graph


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
            return self.known_nodes(ursula)
