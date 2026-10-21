' Conversa com o servidor do PC fora da thread de interface.
'   mode = "cached":  lê a tela inicial guardada no Roku (abre o canal na hora)
'   mode = "feed":    busca a tela inicial no PC e guarda uma cópia
'   mode = "row":     uma lista: da cópia guardada se ainda vale, senão do PC
'   mode = "search":  busca no PC em todas as listas
'   mode = "posters": guarda as capas no espaço do canal, para as próximas aberturas
'   mode = "posterlist": diz quais capas já estão guardadas
'   mode = "play":    pede ao PC para abrir o título; sem PC, abre sozinho quando dá

sub init()
    m.top.functionName = "doWork"
end sub

sub doWork()
    mode = m.top.mode
    if mode = "cached" then
        DeleteFile("cachefs:/feed.json")          ' cópia inteira dos builds 8-11, não é mais usada
        DeleteFile("cachefs:/feed.version")
        text = ReadAsciiFile(homePath())
        data = invalid
        if text <> "" then data = ParseJson(text)
        if data = invalid then
            m.top.error = "sem cópia guardada"
        else
            m.top.result = data
        end if
    else if mode = "feed" then
        ' manda a versão da cópia guardada: se nada mudou, o PC responde só {same: true}
        have = ""
        if m.top.body = invalid or m.top.body.full <> true then have = ReadAsciiFile(homeVersionPath())
        text = request("GET", serverUrl() + "/api/roku?fmt=4&v=" + have, "", 20000)
        if text = invalid and relocateServer() then text = request("GET", serverUrl() + "/api/roku?fmt=4&v=" + have, "", 20000)
        data = invalid
        if text <> invalid then data = ParseJson(text)
        if data = invalid then
            m.top.error = "Não consegui falar com o computador em " + serverUrl() + "."
        else
            if not data.DoesExist("same") then
                WriteAsciiFile(homePath(), text)
                WriteAsciiFile(homeVersionPath(), data.version)
            end if
            m.top.result = data
        end if
    else if mode = "row" then
        loadRow(m.top.body.id, m.top.body.v)
    else if mode = "search" then
        xfer = CreateObject("roUrlTransfer")
        text = request("GET", serverUrl() + "/api/roku/search?q=" + xfer.Escape(m.top.body.q), "", 15000)
        data = invalid
        if text <> invalid then data = ParseJson(text)
        if data = invalid then
            m.top.error = "sem conexão"
        else
            m.top.result = data
        end if
    else if mode = "posters" then
        savePosters(m.top.body.codes)
    else if mode = "posterlist" then
        names = CreateObject("roFileSystem").GetDirectoryListing("cachefs:/p")
        if names = invalid then names = []
        m.top.result = { names: names }
    else if mode = "play" then
        body = m.top.body
        payload = FormatJson({ id: body.id, service: body.service })
        res = requestFull("POST", serverUrl() + "/api/play_title", payload, 20000)
        if res.code = 0 and relocateServer() then res = requestFull("POST", serverUrl() + "/api/play_title", payload, 20000)
        if res.code <> 0 then
            ' o PC respondeu (mesmo com erro): não abre de novo por conta própria
            data = ParseJson(res.text)
            if data = invalid then data = { ok: false, error: "O computador respondeu com erro (" + res.code.ToStr() + ")." }
            data.id = body.id
            m.top.result = data
            return
        end if
        data = playWithoutPC(body.steps)
        data.id = body.id
        m.top.result = data
    end if
end sub

' Uma lista. A tela inicial diz qual versão de cada lista é a atual (want): se a cópia
' guardada é dessa versão, nem pergunta ao PC. Sem PC, usa a cópia que tiver.
sub loadRow(id as string, want as string)
    path = rowPath(id)
    cached = invalid
    text = ReadAsciiFile(path)
    if text <> "" then cached = ParseJson(text)
    if cached <> invalid and not (cached.DoesExist("row") and cached.DoesExist("v")) then cached = invalid
    if cached <> invalid and cached.v = want then
        m.top.result = cached
        return
    end if
    have = ""
    if cached <> invalid then have = cached.v
    xfer = CreateObject("roUrlTransfer")
    url = serverUrl() + "/api/roku/list?id=" + xfer.Escape(id) + "&v=" + have
    text = request("GET", url, "", 20000)
    data = invalid
    if text <> invalid then data = ParseJson(text)
    if data <> invalid and data.DoesExist("same") and cached <> invalid then
        m.top.result = cached
    else if data <> invalid and data.DoesExist("row") then
        WriteAsciiFile(path, text)
        m.top.result = data
    else if cached <> invalid then
        m.top.result = cached
    else
        m.top.error = "Não consegui carregar esta lista do computador."
    end if
end sub

' Baixa as capas que ainda não estão guardadas (no máximo 300 por vez).
sub savePosters(codes as object)
    fs = CreateObject("roFileSystem")
    if not fs.Exists("cachefs:/p") then fs.CreateDirectory("cachefs:/p")
    done = []
    left = []
    port = CreateObject("roMessagePort")
    for each code in codes
        if done.Count() >= 300 then
            left.Push(code)          ' volta para a fila na próxima rodada
        else
            file = posterFile(code)
            if fs.Exists(file) then
                done.Push(code)
            else
                xfer = CreateObject("roUrlTransfer")
                xfer.SetCertificatesFile("common:/certs/ca-bundle.crt")    ' as capas vêm por HTTPS
                xfer.InitClientCertificates()
                xfer.SetMessagePort(port)
                xfer.SetUrl(posterWeb(code))
                ok = false
                if xfer.AsyncGetToFile(file) then
                    msg = wait(10000, port)              ' uma capa travada não para a fila
                    if type(msg) = "roUrlEvent" and msg.GetResponseCode() = 200 then ok = true
                    if not ok then xfer.AsyncCancel()
                end if
                if ok then
                    done.Push(code)
                else
                    DeleteFile(file)      ' não deixa capa pela metade passar por guardada
                end if
            end if
        end if
    end for
    m.top.result = { codes: done, left: left }
end sub

' O PC não respondeu no endereço conhecido: procura na rede e guarda se achar em outro.
function relocateServer() as boolean
    found = findServer()
    if found = "" or found = serverUrl() then return false
    saveServer(found)
    return true
end function

function homePath() as string
    return "cachefs:/home.json"
end function

function homeVersionPath() as string
    return "cachefs:/home.version"
end function

function rowPath(id as string) as string
    return "cachefs:/row_" + id.Replace(":", "_") + ".json"
end function

' Como request, mas diz se houve resposta: code = 0 quando nada respondeu.
function requestFull(method as string, url as string, body as string, timeoutMs as integer) as object
    xfer = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    xfer.SetMessagePort(port)
    xfer.SetUrl(url)
    xfer.AddHeader("Content-Type", "application/json")
    xfer.EnableEncodings(true)
    xfer.RetainBodyOnError(true)
    xfer.SetRequest(method)
    if not xfer.AsyncPostFromString(body) then return { code: 0, text: "" }
    msg = wait(timeoutMs, port)
    if type(msg) = "roUrlEvent" and msg.GetResponseCode() > 0 then return { code: msg.GetResponseCode(), text: msg.GetString() }
    xfer.AsyncCancel()
    return { code: 0, text: "" }
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
