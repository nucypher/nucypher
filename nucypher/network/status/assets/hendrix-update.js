window.onload = function () {
    const origin_hostname = window.location.hostname;
    const socket = new WebSocket("ws://"+ origin_hostname +":9000");
    socket.binaryType = "arraybuffer";

    socket.onopen = function () {
        socket.send(JSON.stringify({'hx_subscribe': 'states'}));
        socket.send(JSON.stringify({'hx_subscribe': 'nodes'}));
        isopen = true;
    }

    socket.addEventListener('message', function (event) {
        console.log("Message from server ", event.data);
        if (event.data.startsWith("[\"states\"")) {
            var hidden_state_button = document.getElementById("hidden-state-button");
            // weird timing issue with onload and DOM element potentially not being created as yet
            if( hidden_state_button != null ) {
                hidden_state_button.click(); // Update states
            }
        } else if (event.data.startsWith("[\"nodes\"")) {
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