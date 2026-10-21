sub init()
    m.top.functionName = "doWork"
end sub

sub doWork()
    xfer = CreateObject("roUrlTransfer")
    xfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    xfer.AddHeader("Content-Type", "application/json")
    xfer.EnableEncodings(true)
    if m.top.mode = "feed" then
        xfer.SetUrl(serverUrl() + "/api/roku")
        text = xfer.GetToString()
        data = ParseJson(text)
        if data = invalid then
            m.top.error = "Não consegui falar com o computador em " + serverUrl() + ". O app.py está rodando?"
        else
            m.top.result = data
        end if
    else if m.top.mode = "play" then
        port = CreateObject("roMessagePort")
        xfer.SetMessagePort(port)
        xfer.SetUrl(serverUrl() + "/api/play_title")
        xfer.SetRequest("POST")
        if xfer.AsyncPostFromString(FormatJson(m.top.body)) then
            msg = wait(15000, port)
            if type(msg) = "roUrlEvent" then
                data = ParseJson(msg.GetString())
                if data <> invalid then
                    m.top.result = data
                    return
                end if
            end if
        end if
        m.top.error = "O computador não respondeu."
    end if
end sub
