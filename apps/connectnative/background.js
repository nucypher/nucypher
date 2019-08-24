
// connect native
const nucypher = browser.runtime.connectNative("nucypher");
var popupWindow;
var password;

nucypher.onMessage.addListener((response) => {
  // response is a key which can be used to decrypt the original image.
  let route = response.route;
  if (response.input.options){
    route = "options";
  }
  if (ports['panel-messages']){
    ports['panel-messages'].postMessage({
      route: route,
      data: response,
    });
  }
  if(ports['content-messages']){
    ports['content-messages'].postMessage({
      route: route,
      data: response,
    });
  }
});
// encd connect native

//callbacks

function NucypherExecute(request) {
  if (request.character === "undefined") {
    delete request.character;
  }
  nucypher.postMessage(request);
};

function NucypherOptions(request) {
  request.options = true;
  request.keyring_password = password;
  request.args = {
    options: true,
  }
  nucypher.postMessage(request);
}

function getPassword(request){
  ports['panel-messages'].postMessage({
    route: 'need-password',
  });
}

function setPassword(data){
  password = data;
  ports['content-messages'].postMessage({
    route: 'setPassword',
    data: data,
  });
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
    'need-password': getPassword,
    setPassword: setPassword,
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
  popupWindow = browser.windows.create(
    {
      type: "detached_panel",
      url: "popup.html",
      width: 600,
      height: 300,
    }
  );
})