' Telas: "home" (fileiras de provas) → ficha da prova (onde assistir e etapas).

sub init()
    m.subtitle = m.top.findNode("subtitle")
    m.hint = m.top.findNode("hint")
    m.message = m.top.findNode("message")
    m.rows = m.top.findNode("rows")
    m.details = m.top.findNode("details")
    m.dTitle = m.top.findNode("dTitle")
    m.dMeta = m.top.findNode("dMeta")
    m.dBr = m.top.findNode("dBr")
    m.dVpn = m.top.findNode("dVpn")
    m.dButtons = m.top.findNode("dButtons")
    m.dStages = m.top.findNode("dStages")
    m.dStatus = m.top.findNode("dStatus")

    m.races = []
    m.current = invalid
    m.rows.observeField("rowItemSelected", "onRaceSelected")
    m.dButtons.observeField("buttonSelected", "onButtonSelected")
    startFeed()
end sub

sub startFeed()
    m.feedTask = CreateObject("roSGNode", "ApiTask")
    m.feedTask.observeField("result", "onFeed")
    m.feedTask.observeField("error", "onFeedError")
    m.feedTask.mode = "feed"
    m.feedTask.control = "RUN"
end sub

sub onFeedError()
    if m.races.Count() > 0 then return
    m.message.text = m.feedTask.error + Chr(10) + "Aperte OK para tentar de novo."
    m.message.visible = true
end sub

sub onFeed()
    data = m.feedTask.result
    if data = invalid or data.races = invalid then return
    m.races = data.races
    if data.offline = true then
        m.subtitle.text = "Sem o computador: mostrando a última cópia guardada."
    else
        m.subtitle.text = data.updatedText
    end if
    live = []
    nextUp = []
    big = []
    all = []
    for i = 0 to m.races.Count() - 1
        r = m.races[i]
        if r.status = "live" then live.Push(i)
        if r.status = "next" then
            if nextUp.Count() < 10 then nextUp.Push(i)
            if r.kind = "Grande Volta" or r.kind = "Monumento" then big.Push(i)
        end if
        if r.status <> "done" then all.Push(i)
    end for
    root = CreateObject("roSGNode", "ContentNode")
    addRow(root, "Acontecendo agora", live)
    addRow(root, "Próximas provas", nextUp)
    addRow(root, "Grandes Voltas e Monumentos", big)
    addRow(root, "Calendário completo", all)
    if root.getChildCount() = 0 then
        m.message.text = "Nenhuma prova no calendário."
        m.message.visible = true
        return
    end if
    m.rows.content = root
    m.message.visible = false
    m.rows.visible = true
    if not m.details.visible then m.rows.setFocus(true)
end sub

sub addRow(root as object, title as string, idxs as object)
    if idxs.Count() = 0 then return
    row = root.createChild("ContentNode")
    row.title = title
    for each i in idxs
        r = m.races[i]
        card = row.createChild("ContentNode")
        card.title = r.name
        card.addFields({ kind: r.kind, when: r.dates + "  ·  " + r.country, brText: r.brShort, vpnText: r.vpnShort,
                         live: (r.status = "live"), idx: i })
    end for
end sub

sub onRaceSelected()
    sel = m.rows.rowItemSelected
    card = m.rows.content.getChild(sel[0]).getChild(sel[1])
    showDetails(m.races[card.getField("idx")])
end sub

sub showDetails(r as object)
    m.current = r
    m.dTitle.text = r.name
    m.dMeta.text = r.kind + "  ·  " + r.country + "  ·  " + r.dates
    m.dBr.text = r.brLines.Join(Chr(10))
    m.dVpn.text = r.vpnLines.Join(Chr(10))
    labels = []
    for each a in r.apps
        labels.Push("Abrir " + a.label)
    end for
    m.dButtons.buttons = labels
    m.dButtons.visible = labels.Count() > 0
    root = CreateObject("roSGNode", "ContentNode")
    for each s in r.stages
        item = root.createChild("ContentNode")
        item.title = s.line
    end for
    m.dStages.content = root
    m.dStatus.text = r.stagesNote
    m.rows.visible = false
    m.details.visible = true
    m.hint.text = ""
    if labels.Count() > 0 then
        m.dButtons.setFocus(true)
    else
        m.dStages.setFocus(true)
    end if
end sub

sub hideDetails()
    m.details.visible = false
    m.rows.visible = true
    m.hint.text = "OK  etapas e onde assistir"
    m.rows.setFocus(true)
end sub

sub onButtonSelected()
    if m.current = invalid then return
    a = m.current.apps[m.dButtons.buttonSelected]
    m.dStatus.text = "Abrindo " + a.label + "..."
    m.launchTask = CreateObject("roSGNode", "ApiTask")
    m.launchTask.observeField("result", "onLaunched")
    m.launchTask.mode = "launch"
    m.launchTask.body = { app: a.id }
    m.launchTask.control = "RUN"
end sub

sub onLaunched()
    if m.launchTask.result.ok <> true then
        m.dStatus.text = "O Roku não deixou abrir o app. Em Configurações > Sistema > Configurações avançadas, ative o controle por apps móveis."
    end if
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if m.races.Count() = 0 and key = "OK" and m.feedTask.state <> "run" then
        m.message.text = "Tentando de novo..."
        startFeed()
        return true
    end if
    if m.details.visible then
        if key = "back" then
            hideDetails()
            return true
        else if key = "right" and m.dButtons.hasFocus() then
            m.dStages.setFocus(true)
            return true
        else if key = "left" and m.dStages.hasFocus() and m.dButtons.visible then
            m.dButtons.setFocus(true)
            return true
        end if
    end if
    return false
end function
