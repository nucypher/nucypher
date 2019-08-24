function onRetrieved(data){
    $("#output").prepend('<div class="logoutput">'+JSON.stringify(data)+'</div>');
}

function onStatus(data){
    $("#output").prepend('<div class="logoutput">'+JSON.stringify(data)+'</div>');
}

function onOptions(data){

    $('#commandform').empty();
    $('#submitbutton').off("click");

    $('#commandform').append(`<input type="hidden" name="character" value="${data.input.character}"></input>`)
    $('#commandform').append(`<input type="hidden" name="action" value="${data.input.action}"></input>`)

    const ui = {
        str: '<div class="form-group"><input class="form-control" type="text"></input></div>',
    }
    $.each(data.result, function(i, o){
        $('#commandform').append(`<label for="${o.name}input">${o.name}</label>`);
        var el = $(ui[o.type])
        $('#commandform').append(el);
        el.find('input').attr('name', `args[${o.name}]`).attr('id', `${o.name}input`);
        el.append(`<small>${o.hint}</small>`);
    })

    $('#submitbutton').attr('disabled', false).on("click", function(){
        let data = {
            keyring_password: $('#passwordinput').val(),
        }
        data = Object.assign(data, $('#commandform').serializeObject())
        bgPort.postMessage({route: "execute", data: data});
    });
}

function fDispatcher(message){
    console.log("fDispatcher:", message);
    const callbacks = {
        'bob.retrieve': onRetrieved,
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
    bgPort.postMessage({
        route: "options",
        data: {
            character: $(this).attr('character'),
            action: $(this).attr('route'),
        },
    });
});
