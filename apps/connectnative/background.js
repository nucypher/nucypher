
// connect native
const nucypher = browser.runtime.connectNative('nucypher')
var password

nucypher.onMessage.addListener((response) => {
  /*
    routes stdio responses from the NuCypher CLI to the
    right places.
  */

  let route = response.route
  console.log(response)
  if (ports['panel-messages']) {
    ports['panel-messages'].postMessage({
      route: route,
      data: response
    })
  }
  if(ports['content-messages']) {
    ports['content-messages'].postMessage({
      route: route,
      data: response
    })
  }
})

function NucypherExecute (request) {
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

function NucypherOptions(request) {
  request.options = true
  request.keyring_password = password
  nucypher.postMessage(request)
}

function getPassword(request) {
  ports['panel-messages'].postMessage({
    route: 'need-password'
  })
}

function setPassword(data) {
  password = data
  if (ports['content-messages']) {
    ports['content-messages'].postMessage({
      route: 'setPassword',
      data: data
    })
  }
}

// browser interaction
var ports = {
  'panel-messages': null,
  'content-messages': null,
}

function Dispatcher (message) {
  const callbacks = {
    execute: NucypherExecute,
    options: NucypherOptions,
    'need-password': getPassword,
    setPassword: setPassword
  }
  if (callbacks[message.route] !== undefined) {
    return callbacks[message.route](message.data)
  }
}

function connected (p) {
  ports[p.name] = p
  ports[p.name].onMessage.addListener(Dispatcher)
}
browser.runtime.onConnect.addListener(connected)

//panel interaction
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
