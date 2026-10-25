sub init()
    m.bg = m.top.findNode("bg")
    m.band = m.top.findNode("band")
    m.kind = m.top.findNode("kind")
    m.live = m.top.findNode("live")
    m.name = m.top.findNode("name")
    m.when = m.top.findNode("when")
    m.br = m.top.findNode("br")
    m.vpn = m.top.findNode("vpn")
end sub

sub onContent()
    c = m.top.itemContent
    if c = invalid then return
    m.name.text = c.title
    m.kind.text = UCase(c.getField("kind"))
    m.when.text = c.getField("when")
    m.br.text = c.getField("brText")
    m.vpn.text = c.getField("vpnText")
    m.live.visible = c.getField("live")
    color = kindColor(c.getField("kind"))
    m.band.color = color
    m.kind.color = color
end sub

sub onFocus()
    if m.top.focusPercent > 0.5 then
        m.bg.color = "0x262A36FF"
    else
        m.bg.color = "0x1A1D26FF"
    end if
end sub

function kindColor(kind as string) as string
    if kind = "Grande Volta" then return "0xE3C16FFF"
    if kind = "Monumento" then return "0xFF7A59FF"
    if kind = "Volta" then return "0x5FD39AFF"
    return "0x6FA8FFFF"
end function
