function onRetrieved(data){
    $("#output").prepend('<div class="logoutput">'+JSON.stringify(data)+'</div>');
}

function onStatus(data){
    $("#output").prepend('<div class="logoutput">'+JSON.stringify(data)+'</div>');
}

function getPassword(){
    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#commandform').append('<h4 style="color:salmon"> please enter your password</h4>');
}

function onGranted(data) {
    const result = JSON.parse(data.result).result;
    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#commandform').append('<div class="alert alert-success" role="alert">Success</div>');
    $('#commandform').append(`<pre>${data.result}</pre>`);
    $('#output').append('')
}


function onOptions(data){

    if (data.error && data.error === "keyring password is required"){
        return getPassword();
    }

    const options = JSON.parse(data.result).result

    $('#commandform').empty();
    $('#submitbutton').off("click");

    $('#commandform').append(`<input type="hidden" name="character" value="${data.input.character}"></input>`)
    $('#commandform').append(`<input type="hidden" name="action" value="${data.input.action}"></input>`)

    const ui = {
        text: '<div class="form-group"><input class="form-control" type="text"></input></div>',
        integer: '<div class="form-group"><input class="form-control" min="1" max="100" type="number"></input></div>',
    }

    $.each(Object.keys(options), function(i, o){
        var type = options[o];
        var name = o.replace("_", " ");


        $('#commandform').append(`<label for="${name}input">${name}</label>`);
        var el = $(ui[type])
        $('#commandform').append(el);
        el.find('input').attr('name', `args[${o}]`).attr('id', `${o}input`);
        if (name === 'expiration'){
            el.find('input').attr('value', '2019-08-29T10:07:50Z' );
        }
        // el.append(`<small>${o.hint}</small>`);
    })

    $('#submitbutton').attr('disabled', false).on("click", function(){
        let data = {
            keyring_password: $('#passwordinput').val(),
        }
        data = Object.assign(data, $('#commandform').serializeObject())
        console.log(data);
        bgPort.postMessage({route: "execute", data: data});
    });
}

function fDispatcher(message){
    const callbacks = {
        'bob.retrieve': onRetrieved,
        'alice.grant': onGranted,
        'need-password': getPassword,
        'status': onStatus,
        'options': onOptions,
    }
    if (callbacks[message.route] !== undefined){
        return callbacks[message.route](message.data);
    }
}

var bgPort = browser.runtime.connect({name: "panel-messages"});
bgPort.onMessage.addListener(fDispatcher);


$('.button').on("click", function(){
    $('#commandform').empty();
    $('#submitbutton').off("click");

    bgPort.postMessage({
        route: "options",
        data: {
            character: $(this).attr('character'),
            action: $(this).attr('route'),
        },
    });
});

$('#passwordbutton').on("click", function(){
    bgPort.postMessage({route: "setPassword", data: $('#passwordinput').val()});
});
