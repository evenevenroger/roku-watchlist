sub init()
    m.p1 = m.top.findNode("p1")
    m.p2 = m.top.findNode("p2")
    m.p3 = m.top.findNode("p3")
    m.name = m.top.findNode("name")
    m.count = m.top.findNode("count")
end sub

sub showContent()
    c = m.top.itemContent
    if c = invalid then return
    m.p1.uri = c.HDPosterUrl
    m.p2.uri = c.SDPosterUrl
    m.p3.uri = c.FHDPosterUrl
    m.name.text = c.title
    m.count.text = c.ShortDescriptionLine1
end sub
