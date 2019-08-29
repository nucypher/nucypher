var browser = browser || chrome;

$("body").find("nucypher").append(
    '<div><div style="height:300px"><img style="height:300px" class="imgcontainer" src="'+browser.runtime.getURL("images/box.png")+'"><img class="coin" style="width:100px;margin-top:50px;" src="'+browser.runtime.getURL("images/coin.gif")+'"></div><span class="label">click to retrieve</span></div>'
);
$("body").find(".coin").hide();

var bgPort = browser.runtime.connect({name: "content-messages"});
var password = null;

function formatId(messageKit){
    return messageKit.slice(0, 10).replace('+', 'x').replace('/', '1');
}

function onRetrieved(data){
    const element_id = formatId(data.input.args['message-kit']);
    var element = $('#' + element_id);
    if (data.result.length){
        let imagedata = JSON.parse(data.result).result.cleartexts[0];
        element.find(".imgcontainer").attr('src', 'data:image/png;base64,' + imagedata).show();
    } else{
        element.find(".imgcontainer").attr('src', browser.runtime.getURL("images/denied.png")).show()
    }
    element.find('.coin').hide();
}

function setPassword(data){
    password = data;
}

function fDispatcher(message){
    const callbacks = {
        'bob.retrieve': onRetrieved,
        setPassword: setPassword,
    }
    if (callbacks[message.route] !== undefined){
        return callbacks[message.route](message.data);
    }
}

bgPort.onMessage.addListener(fDispatcher);

$("body").find("nucypher").on("click", function(){

    if (password) {
        $(this).find('.prompt').remove();
        var data = JSON.parse($(this).attr("data-data"));
        $(this).attr("id", formatId(data['message-kit']));
        $(this).find('.coin').show();
        $(this).find('.imgcontainer').hide().attr(
            'src', browser.runtime.getURL("images/denied.png"));

        const message = {
            route: 'execute',
            data: {
                character: 'bob',
                action: 'retrieve',
                keyring_password: password,
                args: data,
            }
        };

        bgPort.postMessage(message);
    } else {
        alert("Please Open the NuCypher Control Panel and enter a password");
        bgPort.postMessage({
            route: "need-password",
        });
    }
});

