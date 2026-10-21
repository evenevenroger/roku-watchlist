sub init()
    m.p1 = m.top.findNode("p1")
    m.p2 = m.top.findNode("p2")
    m.p3 = m.top.findNode("p3")
    m.name = m.top.findNode("name")
    m.count = m.top.findNode("count")
    m.webs = ["", "", ""]
    m.p1.observeField("loadStatus", "onP1")
    m.p2.observeField("loadStatus", "onP2")
    m.p3.observeField("loadStatus", "onP3")
end sub

' Capa guardada que o sistema apagou: tenta a da internet.
sub retry(p as object, web as string)
    if p.loadStatus = "failed" and web <> "" and p.uri <> web then p.uri = web
end sub

sub onP1()
    retry(m.p1, m.webs[0])
end sub

sub onP2()
    retry(m.p2, m.webs[1])
end sub

sub onP3()
    retry(m.p3, m.webs[2])
end sub

sub showContent()
    c = m.top.itemContent
    if c = invalid then return
    if c.hasField("webs") then m.webs = c.getField("webs")
    m.p1.uri = c.HDPosterUrl
    m.p2.uri = c.SDPosterUrl
    m.p3.uri = c.FHDPosterUrl
    m.name.text = c.title
    m.count.text = c.ShortDescriptionLine1
end sub
