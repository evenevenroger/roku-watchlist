' O servidor (app.py) troca __SERVER__ pelo endereço do PC ao gerar o .zip.
' Se o PC mudar de IP, o canal procura de novo na rede e guarda o endereço novo.
function builtInServer() as string
    return "__SERVER__"
end function

' O endereço achado na rede só vale enquanto o canal instalado for o mesmo:
' um zip novo traz o endereço atual do PC, e esse passa a valer.
function serverUrl() as string
    sec = CreateObject("roRegistrySection", "watchlist")
    saved = sec.Read("server")
    if saved <> "" and sec.Read("server_for") = builtInServer() then return saved
    return builtInServer()
end function

sub saveServer(url as string)
    sec = CreateObject("roRegistrySection", "watchlist")
    sec.Write("server", url)
    sec.Write("server_for", builtInServer())
    sec.Flush()
end sub

' Testa todos os endereços da rede do Roku na porta do servidor, em lotes; devolve "" se não achar.
function findServer() as string
    ' O nome do PC permite recuperar mudanças de IP sem varrer a rede inteira.
    named = "__SERVER_NAME__"
    probe = CreateObject("roUrlTransfer")
    namedPort = CreateObject("roMessagePort")
    probe.SetMessagePort(namedPort)
    probe.SetUrl(named + "/api/status")
    if probe.AsyncGetToString() then
        msg = wait(1500, namedPort)
        if type(msg) = "roUrlEvent" then
            if msg.GetResponseCode() = 200 and msg.GetString().InStr("minha-watchlist") >= 0 then return named
        end if
        probe.AsyncCancel()
    end if
    port = "8790"
    urlParts = builtInServer().Split(":")
    if urlParts.Count() = 3 then port = urlParts[2].Split("/")[0]
    myIp = ""
    addrs = CreateObject("roDeviceInfo").GetIPAddrs()
    for each k in addrs
        candidate = addrs[k]
        if candidate.Split(".").Count() = 4 and Left(candidate, 4) <> "127." then myIp = candidate
    end for
    parts = myIp.Split(".")
    if parts.Count() <> 4 then return ""
    prefix = parts[0] + "." + parts[1] + "." + parts[2] + "."
    msgPort = CreateObject("roMessagePort")
    for start = 1 to 254 step 64
        pending = {}
        for n = start to start + 63
            if n <= 254 and n.ToStr() <> parts[3] then
                xfer = CreateObject("roUrlTransfer")
                xfer.SetMessagePort(msgPort)
                xfer.SetUrl("http://" + prefix + n.ToStr() + ":" + port + "/api/status")
                if xfer.AsyncGetToString() then pending[xfer.GetIdentity().ToStr()] = { x: xfer, n: n }
            end if
        end for
        deadline = CreateObject("roTimespan")
        while pending.Count() > 0 and deadline.TotalMilliseconds() < 1500
            msg = wait(200, msgPort)
            if type(msg) = "roUrlEvent" then
                key = msg.GetSourceIdentity().ToStr()
                if pending.DoesExist(key) then
                    hit = pending[key]
                    pending.Delete(key)
                    if msg.GetResponseCode() = 200 and msg.GetString().InStr("minha-watchlist") >= 0 then
                        for each k in pending
                            pending[k].x.AsyncCancel()
                        end for
                        return "http://" + prefix + hit.n.ToStr() + ":" + port
                    end if
                end if
            end if
        end while
        for each k in pending
            pending[k].x.AsyncCancel()
        end for
    end for
    return ""
end function

' ---------- capas ----------
' O servidor manda só o código da imagem do IMDb; a capa guardada fica em cachefs:/p.
function posterWeb(code as string) as string
    if code = "" or Left(code, 4) = "http" then return code
    return "https://m.media-amazon.com/images/M/" + code + "._V1_QL75_UX220_.jpg"
end function

function posterFile(code as string) as string
    return "cachefs:/p/" + code.Replace("@", "_") + ".jpg"
end function
