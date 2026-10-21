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
    port = builtInServer().Mid(builtInServer().InStr(7, ":") + 1)
    if port = "" then port = "8790"
    myIp = ""
    addrs = CreateObject("roDeviceInfo").GetIPAddrs()
    for each k in addrs
        myIp = addrs[k]
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
