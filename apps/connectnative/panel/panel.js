var password;
const prevdata = {};


//callbacks

function onGenericNucypherReturn(data){
    try {
        clearResults();
        displayResults(JSON.parse(data.result).result);
    } catch {
        displayError(data.result);
    }
}

function onDecrypt(data){
    try {
        results = JSON.parse(data.result).result;
        const cleartexts = results.cleartexts;

        console.log()
        var lg = $('<ul class="list-group"></ul>')
        $('#output').append(lg);
        $.each(cleartexts, function(i, d){
            lg.append(
                `<li class="list-group-item maybeimage"><div class="text">${d}</div></div>`
            );
        });
        const img_lookup = {
            '/' : 'jpg',
            'i' : 'png',
            'r' : 'gif',
        }
        $('.maybeimage').each(function(t){
            $(this).parent().find('.convertimg').remove();
            if (img_lookup[$(this).text().charAt(0)]){
                type=img_lookup[$(this).text().charAt(0)];
                $(this).parent().append(`<button imgtype="${type}"class="btn btn-success convertimg">is this an image?</button>`);
            }
        });

        $('.convertimg').on("click", function(e){
            var el = $(this).prev('.maybeimage')
            var text = el.find('.text').text();
            var img = $('<img src="#"></img');
            el.find('.text').hide();
            img.attr('src', `data:image/${$(this).attr('imgtype')};base64,`+text);
            el.append(img);
            $(this).html("nope not an image.").off("click").on("click", function(e){
                $(this).prev('.maybeimage').find(".text").show();
                $(this).prev('.maybeimage').find("img").remove();
                $(this).remove();
            });
        });
    } catch {
        displayError(data.result);
    }
}

function onGetPassword(){
    clearResults()
    $('#commandform').append('<h4 style="color:salmon"> please enter your password</h4>');
}


function onOptions(data){
    clearResults()
    if (data.error && data.error === "keyring password is required"){
        return onGetPassword();
    }

    $('#commandform').append(`<div class="form-group"><input type="hidden" name="character" value="${data.input.character}"></input></div>`)
    $('#commandform').append(`<div class="form-group"><input type="hidden" name="action" value="${data.input.action}"></input></div>`)

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
            bgPort.postMessage({route: "execute", data: submitdata});
        });
    } catch {
        // json can't be parsed?
        var data = data.result || "NuCypher returned an empty result.";
        displayError(data);
    }
}

// button events
$('.btn.action').on("click", function(){
    clearResults()

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
        'bob.retrieve': onGenericNucypherReturn,
        'alice.grant': onGenericNucypherReturn,
        'alice.decrypt': onDecrypt,
        'enrico.encrypt': onGenericNucypherReturn,
        'need-password': onGetPassword,
        'status': onGenericNucypherReturn,
        'options': onOptions,
    }
    if (callbacks[message.route] !== undefined){
        return callbacks[message.route](message.data);
    }
}

function displayResults(result){
    $('#output').append('<div class="alert alert-success" role="alert">Success</div>');
    var lg = $('<ul class="list-group"></ul>')
    $('#output').append(lg);
    $.each(Object.keys(result), function(i, a){
        lg.append(`<li class="list-group-item"><strong>${a}:</strong> ${result[a]}</li>`)
    })
}

function clearResults(){
    $('#commandform').empty();
    $('#submitbutton').off("click");
    $('#output').empty();
}

function displayError(result){
    $('#output').append('<div class="alert alert-danger" role="alert">Error</div>');
    var lg = $('<ul class="list-group"></ul>')
    $('#output').append(lg);
    lg.append(`<li class="list-group-item"><strong>result:</strong> ${result}</li>`)
}

var bgPort = browser.runtime.connect({name: "panel-messages"});
bgPort.onMessage.addListener(fDispatcher);
