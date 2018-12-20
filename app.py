import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
from plotly.graph_objs import Scatter, Layout, Figure
from plotly.graph_objs.layout import Margin
from plotly.graph_objs.scatter import *
import pandas as pd
import sqlite3
import time

app = dash.Dash(
    'streaming-heartbeat-app'
)
server = app.server

app.layout = html.Div([
    html.Div([
        html.H2("Streaming Heartbeat Demo"),
        html.Img(src="./assets/nucypher_logo.png"),
    ], className='banner'),
    html.Div([
        html.Div([
            html.H3("Heartbeat")
        ], className='Title'),
        html.Div([
            dcc.Graph(id='heartbeat'),
        ], className='twelve columns heartbeat'),
        dcc.Interval(id='heartbeat-update', interval=1000, n_intervals=0),
    ], className='row heartbeat-row')
], style={'padding': '0px 10px 15px 10px',
          'marginLeft': 'auto', 'marginRight': 'auto', "width": "900px",
          'boxShadow': '0px 0px 5px 5px rgba(204,204,204,0.4)'})


@app.callback(Output('heartbeat', 'figure'), [Input('heartbeat-update', 'n_intervals')])
def read_heartbeats(interval):
    db_conn = sqlite3.connect("./data/heartbeats.db")

    now = time.time()
    df = pd.read_sql_query('SELECT Timestamp, HR '
                           'FROM HeartRates '
                           'WHERE Timestamp > "{}" AND Timestamp <= "{}" '
                           'ORDER BY Timestamp;'
                           .format(now - 30, now), db_conn)  # get last 30s of readings
    trace = Scatter(
        y=df['HR'],
        line=Line(
            color='#1E65F3'
        ),
        mode='lines+markers',
    )

    layout = Layout(
        height=450,
        xaxis=dict(
            title='Time Elapsed (sec)',
            range=[0, 30],
            showgrid=False,
            showline=True,
            zeroline=False,
            fixedrange=True,
            tickvals=[0, 10, 20, 30],
            ticktext=['30', '20', '10', '0']
        ),
        yaxis=dict(
            title="Heart Rate (bpm)",
            range=[50, 110],
            showline=True,
            fixedrange=True,
            zeroline=False,
            nticks=10
        ),
        margin=Margin(
            t=45,
            l=50,
            r=50
        )
    )

    return Figure(data=[trace], layout=layout)


if __name__ == '__main__':
    app.run_server()
