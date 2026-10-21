' Conversa com o servidor do PC fora da thread de interface.
'   mode = "cached": lê os últimos dados guardados no Roku (abre o canal na hora)
'   mode = "feed":   busca dados novos no PC e guarda uma cópia
'   mode = "play":   pede ao PC para abrir o título; sem PC, abre sozinho quando dá

sub init()
    m.top.functionName = "doWork"
end sub

sub doWork()
    if m.top.mode = "cached" then
        text = ReadAsciiFile(cachePath())
        data = invalid
        if text <> "" then data = ParseJson(text)
        if data = invalid then
            m.top.error = "sem cópia guardada"
        else
            m.top.result = data
        end if
    else if m.top.mode = "feed" then
        ' manda a versão da cópia guardada: se nada mudou, o PC responde só {same: true}
        have = ""
        if m.top.body = invalid or m.top.body.full <> true then have = ReadAsciiFile(versionPath())
        text = request("GET", serverUrl() + "/api/roku?fmt=2&v=" + have, "", 25000)
        data = invalid
        if text <> invalid then data = ParseJson(text)
        if data = invalid then
            m.top.error = "Não consegui falar com o computador em " + serverUrl() + "."
        else
            if not data.DoesExist("same") then
                WriteAsciiFile(cachePath(), text)
                WriteAsciiFile(versionPath(), data.version)
            end if
            m.top.result = data
        end if
    else if m.top.mode = "play" then
        body = m.top.body
        text = request("POST", serverUrl() + "/api/play_title", FormatJson({ id: body.id, service: body.service }), 8000)
        if text <> invalid then
            data = ParseJson(text)
            if data <> invalid then
                m.top.result = data
                return
            end if
        end if
        m.top.result = playWithoutPC(body.steps)
    end if
end sub

function cachePath() as string
    return "cachefs:/feed.json"
end function

function versionPath() as string
    return "cachefs:/feed.version"
end function

' Requisição com tempo-limite; devolve o corpo ou invalid.
function request(method as string, url as string, body as string, timeoutMs as integer) as dynamic
    xfer = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    xfer.SetMessagePort(port)
    xfer.SetUrl(url)
    xfer.AddHeader("Content-Type", "application/json")
    xfer.EnableEncodings(true)
    started = false
    if method = "GET" then
        started = xfer.AsyncGetToString()
    else
        xfer.SetRequest(method)
        started = xfer.AsyncPostFromString(body)
    end if
    if not started then return invalid
    msg = wait(timeoutMs, port)
    if type(msg) = "roUrlEvent" and msg.GetResponseCode() = 200 then return msg.GetString()
    xfer.AsyncCancel()
    return invalid
end function

' Sem o PC: o próprio canal manda o Roku abrir o app no título (comando ECP local).
' Só funciona para links diretos sem passos extras: ao abrir outro app, este canal
' é fechado e não consegue escolher perfil nem digitar na busca.
function playWithoutPC(steps as dynamic) as object
    if steps = invalid or steps.l = invalid then return { ok: false, error: "O computador não respondeu." }
    if Left(steps.l, 7) <> "launch/" or steps.k.Count() > 0 then
        return { ok: false, error: "O computador não respondeu, e este serviço precisa dele (perfil ou busca). Ligue o PC e tente de novo." }
    end if
    ip = ""
    addrs = CreateObject("roDeviceInfo").GetIPAddrs()
    for each k in addrs
        ip = addrs[k]
    end for
    if ip = "" then return { ok: false, error: "Sem rede." }
    res = request("POST", "http://" + ip + ":8060/" + steps.l, "", 5000)
    if res = invalid then return { ok: false, error: "O computador não respondeu, e o Roku não aceitou abrir o app sozinho." }
    return { ok: true, local: true }
end function
