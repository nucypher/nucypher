
// connect native
const nucypher = browser.runtime.connectNative("nucypher");

nucypher.onMessage.addListener((response) => {
  console.log(response);
  // response is a key which can be used to decrypt the original image.
  if (ports['panel-messages']){
    ports['panel-messages'].postMessage({
      route: response.route,
      data: response,
    });
  }
  if(ports['content-messages']){
    ports['content-messages'].postMessage({
      route: response.route,
      data: response,
    });
  }
});
// encd connect native

//callbacks

function NucypherExecute(request) {
  if (request.character === "undefined"){
    delete request.character;
  }
  console.log(request);
  nucypher.postMessage(request);
};

function NucypherOptions(request) {
  request.options = true;
  nucypher.postMessage(request);
}

// browser interaction
var ports = {
  "panel-messages": null,
  "content-messages": null,
}

function Dispatcher(message){
  const callbacks = {
    execute: NucypherExecute,
    options: NucypherOptions,
  }
  if (callbacks[message.route] !== undefined){
    return callbacks[message.route](message.data);
  }
}

function connected(p) {
  ports[p.name] = p;
  ports[p.name].onMessage.addListener(Dispatcher);
  console.log(ports)
}
browser.runtime.onConnect.addListener(connected);

//panel interaction
browser.browserAction.onClicked.addListener(() => {
  var popupWindow = browser.windows.create(
    {
      type: "detached_panel",
      url: "popup.html",
      width: 600,
      height: 300,
    }
  );
})