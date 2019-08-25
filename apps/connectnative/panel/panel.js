var password;
const prevdata = {};


//callbacks

function onGetPassword(){
    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#commandform').append('<h4 style="color:salmon"> please enter your password</h4>');
}

function onRetrieved(data){
    displayResults(data)
}

function onStatus(data){
    displayResults(data)
}

function onGranted(data) {
    const result = JSON.parse(data.result).result;
    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#commandform').append('<div class="alert alert-success" role="alert">Success</div>');
    displayResults(result);
}

function onOptions(data){

    console.log(prevdata);
    if (data.error && data.error === "keyring password is required"){
        return onGetPassword();
    }

    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#commandform').append(`<input type="hidden" name="character" value="${data.input.character}"></input>`)
    $('#commandform').append(`<input type="hidden" name="action" value="${data.input.action}"></input>`)

    const ui = {
        text: '<div class="form-group"><input class="form-control" type="text"></input></div>',
        integer: '<div class="form-group"><input class="form-control" min="1" max="100" type="number"></input></div>',
    }


    try{
        const options = JSON.parse(data.result).result;
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
        })

        if (prevdata[`${data.character}.${data.action}`]){
            $('#commandform').inputValues(prevdata[`${data.character}.${data.action}`]);
        }

        $('#submitbutton').attr('disabled', false).on("click", function(){
            let submitdata = {
                keyring_password: $('#passwordinput').val(),
            }
            submitdata = Object.assign(submitdata, $('#commandform').serializeObject())
            prevdata[`${submitdata.character}.${submitdata.action}`] = submitdata;

            console.log(prevdata);
            bgPort.postMessage({route: "execute", data: submitdata});
        });
    } catch {
        // json can't be parsed?
        var data = {result: data.result || "NuCypher returned an empty result."};
        displayResults(data);
    }


}

// button events
$('.btn.action').on("click", function(){
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
    password = $('#passwordinput').val()
    $('.nopassword').removeClass('nopassword');
    bgPort.postMessage({route: "setPassword", data: $('#passwordinput').val()});
});

// internal workings
function fDispatcher(message){
    const callbacks = {
        'bob.retrieve': onRetrieved,
        'alice.grant': onGranted,
        'need-password': onGetPassword,
        'status': onStatus,
        'options': onOptions,
    }
    if (callbacks[message.route] !== undefined){
        return callbacks[message.route](message.data);
    }
}

function displayResults(result){
    var lg = $('<ul class="list-group"></ul>')
    $('#commandform').append(lg);
    $.each(Object.keys(result), function(i, a){
        lg.append(`<li class="list-group-item"><strong>${a}:</strong> ${result[a]}</li>`)
    })
}

var bgPort = browser.runtime.connect({name: "panel-messages"});
bgPort.onMessage.addListener(fDispatcher);
