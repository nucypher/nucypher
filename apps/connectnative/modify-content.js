$("body").find("nucypher").append(
    '<div><div><img width="300" src="https://cdn.discordapp.com/attachments/511272975845163019/614224386064384022/box.png"></div>click to retrieve</div>'
);


var bgPort = browser.runtime.connect({name:"port-from-cs"});


bgPort.onMessage.addListener(function(m) {
    $("body").find("nucypher").first().find("img").attr('src', 'data:image/png;base64,' + m);
});


$("body").find("nucypher").on("click", function(){
    var data = JSON.parse($(this).attr("data-data"));
    $(this).attr("id", data.message_kit);
    bgPort.postMessage(data);
});

