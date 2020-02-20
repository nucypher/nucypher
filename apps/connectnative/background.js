
// connect native
const nucypher = browser.runtime.connectNative('nucypher')
var password

// browser interaction
const ports = {
  'panel-messages': null,
  'content-messages': null
}

const STDIOReturnMessageHandler = (response) => {
  /*
    routes stdio responses from the NuCypher CLI to the
    right places.
  */
  const route = response.route
  if (ports['panel-messages']) {
    ports['panel-messages'].postMessage({
      route: route,
      data: response
    })
  }

  if (ports['content-messages']) {
    ports['content-messages'].postMessage({
      route: route,
      data: response
    })
  }
}

const ExecuteSTDIOCommand = (request) => {
  if (request.character === 'undefined') {
    delete request.character
  }
  try {
    nucypher.postMessage(request)
  } catch (err) {
    if (request.action === 'status') {
      ports['panel-messages'].postMessage({
        route: 'status',
        data: 'error'
      })
    }
  }
}


function NucypherOptions (request) {
  request.options = true
  nucypher.postMessage(request)
}

function getPassword (request) {
  ports['panel-messages'].postMessage({
    route: 'need-password'
  })
}

function setPassword (data) {
  password = data
  if (ports['content-messages']) {
    ports['content-messages'].postMessage({
      route: 'setPassword',
      data: data
    })
  }
}

function Dispatcher (message) {
  const callbacks = {
    execute: ExecuteSTDIOCommand,
    options: NucypherOptions,
    setPassword: setPassword
  }
  if (callbacks[message.route] !== undefined) {
    return callbacks[message.route](message.data)
  }
}

function onConnected (p) {
  ports[p.name] = p
  ports[p.name].onMessage.addListener(Dispatcher)
}

browser.runtime.onConnect.addListener(onConnected)
nucypher.onMessage.addListener(STDIOReturnMessageHandler)

// create the UI panel
browser.browserAction.onClicked.addListener(() => {
  popupWindow = browser.windows.create(
    {
      type: 'detached_panel',
      url: 'popup.html',
      width: 600,
      height: 600
    }
  )
})
