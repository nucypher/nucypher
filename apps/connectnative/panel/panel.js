let password = null

function onStatus (data) {
  // just checks that we have communication with NuCypher stdio.

  if (data === 'error') {
    $('.status').addClass('error')
    return
  }
  if (data.route && data.route == 'status') {
    $('.status').addClass('ready')
  }
}

function onDecrypt (data) {
  try {
    const results = JSON.parse(data.result).result
    const cleartexts = results.cleartexts
    var lg = $('<ul class="list-group"></ul>')
    $('#output').append(lg)
    $.each(cleartexts, function (i, d) {
      lg.append(
        `<li class="list-group-item maybeimage"><div class="text">${d}</div></div>`
      )
    })
    const imgLookup = {
      '/': 'jpg',
      i: 'png',
      r: 'gif'
    }
    $('.maybeimage').each(function (t) {
      $(this).parent().find('.convertimg').remove()
      if (imgLookup[$(this).text().charAt(0)]) {
        const type = imgLookup[$(this).text().charAt(0)]
        $(this).parent().append(`<button imgtype="${type}"class="btn-success convertimg">is this an image?</button>`)
      }
    })

    $('.convertimg').on('click', function (e) {
      var el = $(this).prev('.maybeimage')
      var text = el.find('.text').text()
      var img = $('<img src="#"></img')
      el.find('.text').hide()
      img.attr('src', `data:image/${$(this).attr('imgtype')}base64,`+text)
      el.append(img)
      $(this).html('nope not an image.').off('click').on('click', function (e) {
        $(this).prev('.maybeimage').find('.text').show()
        $(this).prev('.maybeimage').find('img').remove()
        $(this).remove()
      })
    })
  } catch {
    displayError(data.result)
  }
}

function onOptions (data) {
  clearResults()
  clearCommands()
  Object.keys(data.result).forEach((name) => {
    let el = $(`<button class="btn-default tm-5 command" route="${data.input.character}.${name}" character="${data.input.character}">${name}</button>`)
      .data(
        { character: data.input.character,
          action: name,
          properties: data.result[name].properties,
          route: `${data.input.character}.${name}`
        })
      .click(function (e) {
        clearResults()
        $('button.command.selected').removeClass('selected')
        $(this).addClass('selected')
        $('.needscommand').show()
        populateCommand($(this).data())
      })
    $('#commandpallette').append(el)
  })
}

function populateCommand (data) {

  $('#commandform').append(`<div><input type="hidden" name="character" value="${data.character}"></input></div>`)
  $('#commandform').append(`<div><input type="hidden" name="action" value="${data.action.replace('_', '-')}"></input></div>`)
  $('#commandform').append('<div><input type="checkbox" name="args[]json_ipc" id="json_ipcinput"><label for="json_ipcinput">results as json</label></div>')

  const ui = {
    text: '<div><input type="text"></input></div>',
    string: '<div><input type="text"></input></div>',
    file: '<div><input type="text" placeholder="a local file path"></input></div>',
    path: '<div><input type="text" placeholder="a local file path"></input></div>',
    integer: '<div><input type="number"></input></div>',
    boolean: '<div><input type="checkbox"></input></div>',
    choice: '<div><select></select></div>',
    textfield: '<div><textarea rows="3"></textarea></input></div>',
    'integer range': '<div><input min="1" max="100" type="number"></input></div>',
  }
  try {
    $.each(Object.keys(data.properties), function (i, o) {
      const param = data.properties[o]
      const type = param.type
      const format = param.format
      const name = o//o.replace('_', ' ')

      let el = ui[format] || ui[type]
      if (!el) {
        console.log(o, param, type)
        el = ui.text
      }
      el = $(el)
      if (type === 'choice') {
        const choices = param.choices
        choices.forEach((c) => {
          el.find('select').append(`<option val="${c}">${c}</option>`)
        })
      }
      el.append(`<label for="${name}input">${name}(${type})</label>`)
      $('#commandform').append(el)
      el.find('input, textarea, select').attr('name', `args[${o}]`).attr('id', `${o}input`)
      if (name === 'expiration') {
        el.find('input').attr('value', '2019-08-29T10:07:50Z')
      }
    })
  } catch (err) {
    // json can't be parsed?
    var output = data.result || 'NuCypher returned an empty result.'
    displayError(output)
  }
  $('#commandform').append($('<button type="submit" id="submitbutton">Go</button>'))
  $('#commandform').submit((e) => {
    e.preventDefault()
    e.stopPropagation()
    let submitdata = {
      keyring_password: $('#passwordinput').val(),
    }
    const formdata = $('#commandform').serializeObject()
    Object.keys(formdata).forEach((k) => {
      submitdata[k] = formdata[k]
    })
    bgPort.postMessage({ route: 'execute', data: submitdata })
  })
}

const setPassword = function () {
  password = $('#passwordinput').val()
  $('.nopassword').removeClass('nopassword')
  bgPort.postMessage({route: "setPassword", data: $('#passwordinput').val()})
}


// internal workings
function fDispatcher (message) {
  const callbacks = {
    'bob.retrieve': onDecrypt,
    'alice.decrypt': onDecrypt,
    status: onStatus,
    options: onOptions
  }
  if (callbacks[message.route] !== undefined) {
    return callbacks[message.route](message.data)
  } else {
    return displayResults(message)
  }
}

function displayResults (message) {
  if (message.data.result) {
    try {
      const resultData = JSON.parse(message.data.result)
      Object.keys(resultData.result).forEach((v) => {
        $('#output').append(
          `<div>${v}: ${resultData.result[v]}</div>`
        )
      })
    } catch (err) {
      $('#output').append(`<pre>${message.data.result}</pre>`)
    }

  } else if (message.data.error) {
    $('#output').append(`<pre>${message.data.error}</pre>`)
  }
}

function clearResults () {
  $('#commandform').empty()
  $('#submitbutton').off("click")
  // $('#output').empty()
}

function clearCommands () {
  $('#commandpallette').empty()
}

function displayError (result) {
  $('#output').append('<div class="alert alert-danger" role="alert">Error</div>')
  var lg = $('<ul class="list-group"></ul>')
  $('#output').append(lg)
  lg.append(`<li class="list-group-item"><strong>result:</strong> ${result}</li>`)
}


$('#passwordbutton').on('click', setPassword)
$('#passwordform').submit((e) => {
  e.preventDefault()
  e.stopPropagation()
  setPassword()
})


// button events
$('.character').on('click', function () {
  $('a.selected').removeClass('selected')
  $('.needscommand').hide()
  $(this).addClass('selected')
  $('.needscharacter').show()
  clearResults()
  bgPort.postMessage({
    route: 'options',
    data: {
      character: $(this).attr('character'),
    }
  })
})

var bgPort = browser.runtime.connect({name: "panel-messages"})
bgPort.onMessage.addListener(fDispatcher)

// startup installation check
setTimeout(()=>{
  bgPort.postMessage({route: "execute", data: {action: "status"}})
}, 500)
