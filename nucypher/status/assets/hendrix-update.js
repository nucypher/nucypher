window.onload = function () {
    const origin_hostname = window.location.hostname;
    const socket = new WebSocket("ws://"+ origin_hostname +":9000");
    socket.binaryType = "arraybuffer";

    socket.onopen = function () {
        socket.send(JSON.stringify({'hx_subscribe': 'states'}));
        socket.send(JSON.stringify({'hx_subscribe': 'nodes'}));
        socket.send(JSON.stringify({'hx_subscribe': 'teachers'}));
        isopen = true;
    }

    socket.addEventListener('message', function (event) {
        console.log("Message from server ", event.data);
        if (event.data.startsWith("[\"states\"")) {
            document.getElementById("hidden-state-button").click(); // Update states
        } else if (event.data.startsWith("[\"nodes\"")) {
            document.getElementById("hidden-node-button").click(); // Update nodes
        }
    });

    socket.onerror = function (error) {
        console.log(error.data);
    }
}