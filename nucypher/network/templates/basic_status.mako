<%!
def hex_to_rgb(color_hex):
    # Expects a color in the form "#abcdef"
    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    return r, g, b

def contrast_color(color_hex):
    r, g, b = hex_to_rgb(color_hex)
    # As defined in https://www.w3.org/WAI/ER/WD-AERT/#color-contrast
    # Ranges from 0 to 255
    intensity = (r * 299 + g * 587 + b * 114) / 1000
    if intensity > 128:
        return "black"
    else:
        return "white"

def character_span(character):
    color = character.color_hex
    symbol = character.symbol
    return f'<span class="symbol" style="color: {contrast_color(color)}; background-color: {color}">{symbol}</span>'
%>

<%def name="fleet_state_icon(state)">
%if not state:
<span style="color: #CCCCCC">&mdash;</span>
%else:
<table class="state-info" title="${state.nickname}">
    <tr>
        <td>
            ## Need to compose these spans as strings to avoid introducing whitespaces
            <span class="state-icon">${"".join(character_span(character) for character in state.nickname.characters)}</span>
        </td>
        <td>
            <span>${state.population} nodes</span>
            <br/>
            <span class="checksum">${state.checksum[0:8]}</span>
        </td>
    </tr>
</table>
%endif
</%def>


<%def name="node_info(node)">
<div>
    <table class="node-info">
        <tr>
            <td>
                ## Need to compose these spans as strings to avoid introducing whitespaces
                <span class="node-icon">${"".join(character_span(character) for character in node.nickname.characters)}</span>
            </td>
            <td>
                <a href="https://${node.rest_url}/status">
                <span class="nickname">${ node.nickname }</span>
                </a>
                <br/>
                <span class="checksum">${ node.staker_address }</span>
            </td>
        </tr>
    </table>
</div>
</%def>


<%def name="main(status_info)">
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="icon" type="image/x-icon" href="https://www.nucypher.com/favicon-32x32.png"/>
    <link rel="stylesheet" type="text/css" href="https://fonts.googleapis.com/css?family=Open+Sans" />
</head>
<style type="text/css">

    body {
        font-family: "Open Sans", sans-serif;
        margin: 2em 2em 2em 2em;
    }

    /* unvisited link */
    a:link {
        color: #115;
        text-decoration-color: #bbb;
    }

    /* visited link */
    a:visited {
        color: #626;
    }

    table.node-info > tr > td {
        padding: 0 0em;
    }

    table.state-info {
        float: left;
        padding: 0 1em 0 0;
    }

    table.state-info > tr > td {
        padding: 0 0em;
    }

    table.known-nodes > tbody > tr > td {
        padding: 0 1em 0 0;
    }

    table.known-nodes > thead > tr > td {
        border-bottom: 1px solid #ddd;
    }

    table.known-nodes > tbody > tr > td {
        border-bottom: 1px solid #ddd;
    }

    .this-node-info {
        margin-bottom: 2em;
    }

    h3 {
        margin-bottom: 0em;
    }

    .this-node {
        font-size: x-large;
    }

    .nickname {
        font-weight: bold;
    }

    .node-icon {
        font-size: 2em;
        font-family: monospace;
        margin-right: 0.2em;
    }

    .state-icon {
        font-size: 2em;
        font-family: monospace;
        margin-right: 0.2em;
    }

    .symbol {
        padding-left: 0.05em;
        padding-right: 0.05em;
    }

    .checksum {
        font-family: monospace;
    }
</style>
</body>

    <table class="this-node-info">
        <tr>
            <td></td>
            <td><div class="this-node">${node_info(status_info)}</div></td>
        </tr>
        <tr>
            <td><div style="margin-bottom: 1em"></div></td>
            <td></td>
        </tr>
        <tr>
            <td><i>Running:</i></td>
            <td>v${ status_info.version }</td>
        </tr>
        <tr>
            <td><i>Domain:</i></td>
            <td>${ status_info.domain }</td>
        </tr>
        <tr>
            <td><i>Fleet state:</i></td>
            <td>${fleet_state_icon(status_info.fleet_state)}</td>
        </tr>
        <tr>
            <td><i>Previous states:</i></td>
            <td>
                %for state in status_info.previous_fleet_states:
                    ${fleet_state_icon(state)}
                %endfor
            </td>
        </tr>
    </table>

    %if status_info.known_nodes is not None:
    <%
        verified_nodes = [node_status for node_status in status_info.known_nodes if node_status.verified]
        unverified_nodes = [node_status for node_status in status_info.known_nodes if not node_status.verified]
    %>
    %for node_set, qualifier in [(verified_nodes, "verified"), (unverified_nodes, "unverified")]:
    <h3>${len(node_set)} ${qualifier} ${"node" if len(node_set) == 1 else "nodes"}:</h3>

    <table class="known-nodes">
        <thead>
            <td></td>
            <td>Launched</td>
            <td style="padding-right: 1em">Last Learned From</td>
            <td>Fleet State</td>
        </thead>
        <tbody>
        %for node in node_set:
            <tr>
                <td>${node_info(node)}</td>
                <td>${node.timestamp.iso8601()}</td>
                <td>
                %if node.last_learned_from is not None:
                ${node.last_learned_from.iso8601()}
                %else:
                <span style="color: #CCCCCC">&mdash;</span>
                %endif
                </td>
                <td>${fleet_state_icon(node.recorded_fleet_state)}</td>
            </tr>
        %endfor
        </tbody>
    </table>
    %endfor
    %endif
</body>
</html>
</%def>
