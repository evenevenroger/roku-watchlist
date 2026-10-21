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
end sub

function field(c as object, name as string, fallback as dynamic) as dynamic
    if c.hasField(name) then return c.getField(name)
    return fallback
end function

sub showContent()
    c = m.top.itemContent
    if c = invalid then return
    m.poster.uri = c.HDPosterUrl
    m.title.text = c.title
    m.svc.text = c.ShortDescriptionLine2

    m.imdb.text = c.ShortDescriptionLine1
    m.imdbBg.visible = (c.ShortDescriptionLine1 <> "")

    mine = field(c, "mineText", "")
    m.mine.text = mine
    m.mineBg.visible = (mine <> "")

    ' faixa do prêmio no pé do pôster
    stripText = field(c, "stripText", "")
    m.strip.visible = (stripText <> "")
    if stripText <> "" then
        won = field(c, "stripWon", false)
        icon = field(c, "stripIcon", "trophy")
        m.stripText.text = UCase(stripText)
        if won then
            m.stripBg.color = "0xE3C16FFF"
            m.stripText.color = "0x2A2008FF"
            m.stripLine.visible = false
            m.stripIcon.uri = "pkg:/images/" + icon + "_dark.png"
        else
            m.stripBg.color = "0x0E0F13E0"
            m.stripText.color = "0xE3C16FFF"
            m.stripLine.visible = true
            m.stripIcon.uri = "pkg:/images/" + icon + "_gold.png"
        end if
    end if

    ' Rotten Tomatoes logo acima da faixa (ou no pé, se não houver faixa)
    rtC = field(c, "rtC", "")
    rtA = field(c, "rtA", "")
    m.rt.visible = (rtC <> "" or rtA <> "")
    if m.rt.visible then
        m.rtC.text = pct(rtC)
        m.rtA.text = pct(rtA)
        if stripText <> "" then
            m.rt.translation = [8, 264]
        else
            m.rt.translation = [8, 292]
        end if
    end if
end sub

function pct(v as string) as string
    if v = "" then return "-"
    return v + "%"
end function
