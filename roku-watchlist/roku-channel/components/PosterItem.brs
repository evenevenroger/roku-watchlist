sub init()
    m.poster = m.top.findNode("poster")
    m.title = m.top.findNode("title")
    m.svc = m.top.findNode("svc")
    m.imdb = m.top.findNode("imdb")
    m.imdbBg = m.top.findNode("imdbBg")
    m.mine = m.top.findNode("mine")
    m.mineBg = m.top.findNode("mineBg")
    m.rt = m.top.findNode("rt")
    m.rtC = m.top.findNode("rtC")
    m.rtA = m.top.findNode("rtA")
    m.strip = m.top.findNode("strip")
    m.stripBg = m.top.findNode("stripBg")
    m.stripLine = m.top.findNode("stripLine")
    m.stripIcon = m.top.findNode("stripIcon")
    m.stripText = m.top.findNode("stripText")
    m.strip2 = m.top.findNode("strip2")
    m.strip2Bg = m.top.findNode("strip2Bg")
    m.strip2Line = m.top.findNode("strip2Line")
    m.strip2Icon = m.top.findNode("strip2Icon")
    m.strip2Text = m.top.findNode("strip2Text")
    m.web = ""
    m.poster.observeField("loadStatus", "onPosterStatus")
end sub

' A capa guardada no Roku pode ter sido apagada pelo sistema: tenta a da internet.
sub onPosterStatus()
    if m.poster.loadStatus = "failed" and m.web <> "" and m.poster.uri <> m.web then m.poster.uri = m.web
end sub

function field(c as object, name as string, fallback as dynamic) as dynamic
    if c.hasField(name) then return c.getField(name)
    return fallback
end function

sub showContent()
    c = m.top.itemContent
    if c = invalid then return
    m.web = field(c, "posterWeb", "")
    m.poster.uri = c.HDPosterUrl
    m.title.text = c.title
    m.svc.text = c.ShortDescriptionLine2

    m.imdb.text = c.ShortDescriptionLine1
    m.imdbBg.visible = (c.ShortDescriptionLine1 <> "")

    mine = field(c, "mineText", "")
    m.mine.text = mine
    m.mineBg.visible = (mine <> "")

    ' faixas de prêmio no pé do pôster: a primeira embaixo, a segunda logo acima
    stripText = field(c, "stripText", "")
    strip2Text = field(c, "strip2Text", "")
    paintStrip(m.strip, m.stripBg, m.stripLine, m.stripIcon, m.stripText, stripText, field(c, "stripWon", false), field(c, "stripIcon", "trophy"))
    paintStrip(m.strip2, m.strip2Bg, m.strip2Line, m.strip2Icon, m.strip2Text, strip2Text, field(c, "strip2Won", false), field(c, "strip2Icon", "trophy"))

    ' Rotten Tomatoes logo acima da faixa (ou no pé, se não houver faixa)
    rtC = field(c, "rtC", "")
    rtA = field(c, "rtA", "")
    m.rt.visible = (rtC <> "" or rtA <> "")
    if m.rt.visible then
        m.rtC.text = pct(rtC)
        m.rtA.text = pct(rtA)
        if strip2Text <> "" then
            m.rt.translation = [8, 232]
        else if stripText <> "" then
            m.rt.translation = [8, 264]
        else
            m.rt.translation = [8, 292]
        end if
    end if
end sub

sub paintStrip(group as object, bg as object, line as object, icon as object, label as object, text as string, won as boolean, iconName as string)
    group.visible = (text <> "")
    if text = "" then return
    label.text = UCase(text)
    if won then
        bg.color = "0xE3C16FFF"
        label.color = "0x2A2008FF"
        line.visible = false
        icon.uri = "pkg:/images/" + iconName + "_dark.png"
    else
        bg.color = "0x0E0F13E0"
        label.color = "0xE3C16FFF"
        line.visible = true
        icon.uri = "pkg:/images/" + iconName + "_gold.png"
    end if
end sub

function pct(v as string) as string
    if v = "" then return "-"
    return v + "%"
end function
