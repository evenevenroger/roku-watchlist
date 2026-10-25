' Tarefas fora da thread de interface.
'   mode = "feed":   calendário e onde assistir, do PC; sem o PC, a última cópia guardada
'   mode = "launch": abre outro app do Roku (body.app = id do canal) pelo controle de rede do próprio Roku

sub init()
    m.top.functionName = "doWork"
end sub

sub doWork()
    mode = m.top.mode
    if mode = "feed" then
        text = request(serverUrl() + "/api/ciclismo", 20000)
        if text = invalid and relocateServer() then text = request(serverUrl() + "/api/ciclismo", 20000)
        data = invalid
        if text <> invalid then data = ParseJson(text)
        if data <> invalid and data.races <> invalid then
            WriteAsciiFile(cachePath(), text)
            m.top.result = data
            return
        end if
        saved = ReadAsciiFile(cachePath())
        if saved <> "" then data = ParseJson(saved)
        if data <> invalid and data.races <> invalid then
            data.offline = true
            m.top.result = data
        else
            m.top.error = "Não consegui falar com o computador em " + serverUrl() + "."
        end if
    else if mode = "launch" then
        ip = ""
        addrs = CreateObject("roDeviceInfo").GetIPAddrs()
        for each k in addrs
            ip = addrs[k]
        end for
        ok = false
        if ip <> "" then ok = (post("http://" + ip + ":8060/launch/" + m.top.body.app, 5000) <> invalid)
        m.top.result = { ok: ok }
    end if
end sub

function cachePath() as string
    return "cachefs:/ciclismo.json"
end function

function relocateServer() as boolean
    found = findServer()
    if found = "" or found = serverUrl() then return false
    saveServer(found)
    return true
end function

' GET com tempo-limite; devolve o corpo ou invalid.
function request(url as string, timeoutMs as integer) as dynamic
    xfer = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    xfer.SetMessagePort(port)
    xfer.SetUrl(url)
    xfer.EnableEncodings(true)
    if not xfer.AsyncGetToString() then return invalid
    msg = wait(timeoutMs, port)
    if type(msg) = "roUrlEvent" and msg.GetResponseCode() = 200 then return msg.GetString()
    xfer.AsyncCancel()
    return invalid
end function

function post(url as string, timeoutMs as integer) as dynamic
    xfer = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    xfer.SetMessagePort(port)
    xfer.SetUrl(url)
    xfer.SetRequest("POST")
    if not xfer.AsyncPostFromString("") then return invalid
    msg = wait(timeoutMs, port)
    if type(msg) = "roUrlEvent" and msg.GetResponseCode() = 200 then return msg.GetString()
    xfer.AsyncCancel()
    return invalid
end function
