import os
from datetime import datetime, timedelta
from os.path import dirname, abspath
from string import Template

import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from dash.dependencies import Output, Input
from maya import MayaDT

from nucypher.blockchain.eth.token import NU
from nucypher.network.status_app.base import NetworkStatusPage


class MoeStatusApp(NetworkStatusPage):
    """
    Status application for 'Moe' monitoring node.
    """

    TEMPLATE_DIR = os.path.join(abspath(dirname(__file__)), 'templates')
    REFRESH_RATE = 60 * 1000

    GRAPH_CONFIG = {'displaylogo': False,
                    'autosizable': True,
                    'responsive': True,
                    'fillFrame': False,
                    'displayModeBar': False}

    def __init__(self, moe, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.moe = moe

        from nucypher.network.status_app.crawler import MoeBlockchainCrawler
        self.moe_crawler = MoeBlockchainCrawler(moe=moe)
        self.moe_crawler.start()

        self.moe_db_client = self.moe_crawler.get_db_client()

        # updates can be directly provided included in javascript snippet
        # TODO: Configurable template path
        template_path = os.path.join(self.TEMPLATE_DIR, 'moe.html')
        with open(template_path, 'r') as file:
            moe_template = file.read()
            self.dash_app.index_string = Template(moe_template).substitute(ws_port=self.moe.websocket_port,
                                                                           ws_host=self.moe.host)

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

                    # Stats
                    html.Div([
                        html.Div(id='current-period'),
                        html.Div(id='time-remaining'),
                        html.Div(id='domains'),
                        html.Div(id='active-stakers'),
                        html.Div(id='staked-tokens'),
                    ], id='stats'),

                    # Charts
                    html.Div([
                        html.Div(id='prev-num-stakers-graph'),
                        html.Div(id='prev-locked-stake-graph'),
                        html.Div(id='locked-stake-graph'),
                    ], id='widgets'),

                    # States and Known Nodes Table
                    html.Div([
                        html.Div(id='prev-states'),
                        html.Br(),
                        html.Div(id='known-nodes'),
                    ])
                ]),

            ], id='main'),

            dcc.Interval(
                id='interval-component',
                interval=self.REFRESH_RATE,
                n_intervals=0
            )
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
                                [Input('interval-component', 'n_intervals')])
        def active_stakers(n):
            staker_addresses = moe.staking_agent.get_stakers()
            return html.Div([html.H4("Active Ursulas"),
                             html.H5(f"{len(moe.known_nodes)}/{len(staker_addresses)}")])

        @self.dash_app.callback(Output('current-period', 'children'),
                                [Input('interval-component', 'n_intervals')])
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

        @self.dash_app.callback(Output('domains', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = ' | '.join(moe.learning_domains)
            return html.Div([
                html.H4('Learning Domains'),
                html.H5(domains),
            ])

        @self.dash_app.callback(Output('staked-tokens', 'children'),
                                [Input('interval-component', 'n_intervals')])
        def staked_tokens(pathname):
            nu = NU.from_nunits(moe.staking_agent.get_global_locked_tokens())
            return html.Div([
                html.H4('Staked Tokens'),
                html.H5(f"{nu}"),
            ])

        @self.dash_app.callback(Output('prev-locked-stake-graph', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def prev_locked_tokens(pathname):
            prior_periods = 30
            locked_tokens_dict = self.moe_db_client.get_historical_locked_tokens_over_range(prior_periods)
            token_values = list(locked_tokens_dict.values())
            fig = go.Figure(data=[
                                go.Bar(
                                    textposition='auto',
                                    x=list(locked_tokens_dict.keys()),
                                    y=token_values,
                                    name='Locked Stake',
                                    marker=go.bar.Marker(color=token_values, colorscale='Viridis')
                                )
                            ],
                            layout=go.Layout(
                                title=f'Staked NU over the previous {prior_periods} days.',
                                xaxis={'title': 'Date', 'nticks': len(locked_tokens_dict) + 1},
                                yaxis={'title': 'NU Tokens', 'zeroline': False, 'rangemode': 'tozero'},
                                showlegend=False,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            ))

            fig['layout'].update(autosize=True, width=None, height=None)
            return dcc.Graph(figure=fig, id='prev-locked-graph', config=self.GRAPH_CONFIG)

        @self.dash_app.callback(Output('prev-num-stakers-graph', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def historical_known_nodes(pathname):
            prior_periods = 30
            num_stakers_dict = self.moe_db_client.get_historical_num_stakers_over_range(prior_periods)
            marker_color = 'rgb(0, 163, 239)'
            fig = go.Figure(data=[
                                go.Scatter(
                                    mode='lines+markers',
                                    x=list(num_stakers_dict.keys()),
                                    y=list(num_stakers_dict.values()),
                                    name='Num Stakers',
                                    marker={'color': marker_color}
                                )
                            ],
                            layout=go.Layout(
                                title=f'Num Stakers over the previous {prior_periods} days.',
                                xaxis={'title': 'Date', 'nticks': len(num_stakers_dict) + 1, 'showgrid': False},
                                yaxis={'title': 'Stakers', 'zeroline': False, 'showgrid': False, 'rangemode': 'tozero'},
                                showlegend=False,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            ))

            fig['layout'].update(autosize=True, width=None, height=None)
            return dcc.Graph(figure=fig, id='prev-stakers-graph', config=self.GRAPH_CONFIG)

        @self.dash_app.callback(Output('locked-stake-graph', 'children'),
                                [Input('url', 'pathname')])
        def future_locked_tokens(pathname):
            token_counter = self.moe_crawler.snapshot['future_locked_tokens']
            periods = len(token_counter)
            period_range = list(range(1, periods + 1))
            token_counter_values = list(token_counter.values())
            fig = go.Figure(data=[
                                go.Bar(
                                    textposition='auto',
                                    x=period_range,
                                    y=token_counter_values,
                                    name='Stake',
                                    marker=go.bar.Marker(color=token_counter_values, colorscale='Viridis')
                                )
                            ],
                            layout=go.Layout(
                                title=f'Staked NU over the next {periods} days.',
                                xaxis={'title': 'Days'},
                                yaxis={'title': 'NU Tokens', 'rangemode': 'tozero'},
                                showlegend=False,
                                legend=go.layout.Legend(x=0, y=1.0),
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)'
                            ))

            fig['layout'].update(autosize=True, width=None, height=None)
            return dcc.Graph(figure=fig, id='locked-graph', config=self.GRAPH_CONFIG)
