
$("body").find("nucypher").append(
    '<div><div style="height:300px"><img style="height:300px" class="imgcontainer" src="'+browser.runtime.getURL("images/box.png")+'"><img class="coin" style="width:100px;margin-top:50px;" src="'+browser.runtime.getURL("images/coin.gif")+'"></div><span class="label">click to retrieve</span></div>'
);
$("body").find(".coin").hide();

function getFakeData(element_id){
    return {
        key: "b98f623efffec330da5a2d0e63f1c9269ea45ac690ce6b26b412ff7d4acb33af",
        image: "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",
        id: element_id,
    };
}

var bgPort = browser.runtime.connect({name:"port-from-cs"});

function onRetrieved(data){
    const element_id = data.input.args['message-kit'].slice(12, 17);
    var element = $('#' + element_id);

    let imagedata = data.result;
    element.find(".imgcontainer").attr('src', 'data:image/png;base64,' + data.image).show();
    element.find('.coin').hide();
}

function fDispatcher(message){
    console.log("fDispatcher:", message);
    const callbacks = {
        'retrieved': onRetrieved,
    }
    return callbacks[message.route](message.data);
}

bgPort.onMessage.addListener(fDispatcher);

$("body").find("nucypher").on("click", function(){
    var data = JSON.parse($(this).attr("data-data"));
    $(this).attr("id", data['message-kit'].slice(12, 17));
    $(this).find('.coin').show();
    $(this).find('.imgcontainer').hide().attr(
        'src', browser.runtime.getURL("images/denied.png"));
    const message = {
        route: 'retrieve',
        data: data,
    };
    bgPort.postMessage(message);
});

