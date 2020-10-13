<%def name="fleet_state_icon(checksum, nickname, population)">
%if not checksum:
NO FLEET STATE AVAILABLE
%else:
<%
    # FIXME: generalize in case we want to extend the number of symbols in the state nickname
    color = nickname.characters[0].color_hex
    symbol = nickname.characters[0].symbol
    short_checksum = checksum[0:8]
%>
<div class="nucypher-nickname-icon" style="border-color:${color};">
<div class="small">${population} nodes</div>
<div class="symbols">
    <span class="single-symbol" style="color: ${color}">${symbol}</span>
</div>
<br/>
<span class="small-address">${short_checksum}</span>
</div>
%endif
</%def>

<%def name="main()">
<!DOCTYPE html>
<html>
<head>
     <meta charset="UTF-8">
     <link rel="icon" type="image/x-icon" href="https://www.nucypher.com/favicon-32x32.png"/>
</head>

<style type="text/css">
    html {
        font-family: sans-serif;
    }
    table, th, td {
        border: 1px solid black;
    }
    .nucypher-nickname-icon {
        border-width: 10px;
        border-style: solid;
        margin: 3px;
        padding: 3px;
        text-align: center;
        box-shadow: 1px 1px black, -1px -1px black;
        width: 100px;
    }
    .small {
        float:left;
        width: 100%;
        text-shadow: none;
        font-family: sans;
        font-size: 10px;
    }
    .symbols {
        float:left;
        width: 100%;
    }
    .single-symbol {
        font-size: 3em;
        color: black;
        text-shadow: 1px 1px black, -1px -1px black;
    }
    .address, .small-address {
        font-family: monospace;
    }
    .small-address {
        text-shadow: none;
    }

    .state {
        float:left;
    }
    #previous-states {
        float:left;
        clear:left;
    }

    #previous-states .state {
        margin:left: 10px;
        border-right: 3px solid black;
    }

    #previous-states .nucypher-nickname-icon {
        height:75px;
        width: 75px;
    }

    #previous-states .single-symbol {
        font-size: 2em;
    }

    #known-nodes {
        float:left;
        clear:left;
    }
    .small-address {
        text-shadow: none;
    }

    .state {
        float:left;
    }
    #previous-states {
        float:left;
        clear:left;
    }

    #previous-states .state {
        margin:left: 10px;
        border-right: 3px solid black;
    }

    #previous-states .nucypher-nickname-icon {
        height:75px;
        width: 75px;
    }

    #previous-states .single-symbol {
        font-size: 2em;
    }

    #known-nodes {
        float:left;
        clear:left;
    }
</style>

<div id="this-node">
    <h2>${ this_node.nickname }</h2>
    <h5>(${ checksum_address })</h5>
    ${ this_node.nickname_icon }
    <h4>v${ version }</h4>
    <h4>Domain: ${ domain }</h4>

    <h3>Fleet State</h3>
    <div class="state">
        <h4>${ known_nodes.nickname }</h4>
        ${ known_nodes.icon }
        <br/>
        <span class="small">${ known_nodes.updated }</span>
        </ul>
    </div>

    <div id="previous-states">
        <h3>Previous States</h3>
        %for state in previous_states:
            <div class="state">
                <h5>${ state.nickname }</h5>
                ${ state.icon }
                <br/>
                <span class="small">${ state.updated }</span>
            </div>
        %endfor
    </div>
</div>
<div id="known-nodes">
    <h4>Known Nodes:</h4>
    <table>
        <thead>
            <td>Icon</td>
            <td>Nickname / Checksum</td>
            <td>Launched</td>
            <td>Last Seen</td>
            <td>Fleet State</td>
        </thead>
        %for node in known_nodes:
            <tr>
                <td>${ node.nickname_icon }</td>
                <td>
                    <a href="https://${node.rest_url()}/status">${ node.nickname }</a>
                    <br/><span class="small">${ node.checksum_address }</span>
                </td>
                <td>${ node.timestamp }</td>
                <td>${ node.last_seen }</td>
                <td>${fleet_state_icon(node.fleet_state_checksum,
                                       node.fleet_state_nickname,
                                       node.fleet_state_population)}</td>
            </tr>
        %endfor
    </table>
</div>
</html>
</%def>
