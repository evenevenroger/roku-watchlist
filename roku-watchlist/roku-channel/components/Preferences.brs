' Preferências compartilhadas. O registro do Roku também conserva alterações sem PC.
sub initPreferences()
    sec = CreateObject("roRegistrySection", "watchlist")
    m.prefs = invalid
    raw = sec.Read("preferences")
    if raw <> "" then m.prefs = ParseJson(raw)
    if m.prefs = invalid then m.prefs = { revision: 0, unseen: m.unseen, lists: {} }
    m.prefPending = invalid
    raw = sec.Read("pending_preferences")
    if raw <> "" then m.prefPending = ParseJson(raw)
    if m.prefPending = invalid then m.prefPending = {}
    m.prefSending = {}
    m.prefTask = invalid
    m.restoringPosition = false
    m.unseen = m.prefs.unseen
    m.prefsTimer = m.top.findNode("prefsTimer")
    m.prefsTimer.observeField("fire", "refreshPreferences")
    m.prefsTimer.control = "start"
    m.savePrefsTimer = m.top.findNode("savePrefsTimer")
    m.savePrefsTimer.observeField("fire", "flushPreferences")
end sub

function mergePreferences(base as object, patch as object) as object
    out = ParseJson(FormatJson(base))
    for each key in patch
        if key <> "lists" then out[key] = patch[key]
    end for
    if patch.DoesExist("unseen") and out.DoesExist("lists") then
        for each id in out.lists
            if patch.unseen then out.lists[id].seen = 1 else out.lists[id].seen = 0
        end for
    end if
    if patch.DoesExist("lists") then
        if not out.DoesExist("lists") then out.lists = {}
        for each id in patch.lists
            if not out.lists.DoesExist(id) then out.lists[id] = {}
            for each key in patch.lists[id]
                out.lists[id][key] = patch.lists[id][key]
            end for
        end for
    end if
    return out
end function

sub storePreferences()
    sec = CreateObject("roRegistrySection", "watchlist")
    sec.Write("preferences", FormatJson(m.prefs))
    ' Inclui o lote em trânsito para não perdê-lo se outro app fechar este canal.
    sec.Write("pending_preferences", FormatJson(mergePreferences(m.prefSending, m.prefPending)))
    sec.Flush()
end sub

sub queuePreferences(patch as object)
    m.prefs = mergePreferences(m.prefs, patch)
    m.prefPending = mergePreferences(m.prefPending, patch)
    storePreferences()
    m.savePrefsTimer.control = "stop"
    m.savePrefsTimer.control = "start"
end sub

sub refreshPreferences()
    if m.prefTask <> invalid then
        if m.prefTask.state = "run" then return
    end if
    m.prefTask = CreateObject("roSGNode", "ApiTask")
    m.prefTask.observeField("result", "onPreferences")
    m.prefTask.observeField("error", "onPreferencesError")
    if m.prefPending.Count() > 0 then
        m.prefSending = m.prefPending
        m.prefPending = {}
        m.prefTask.mode = "saveprefs"
        m.prefTask.body = m.prefSending
    else
        m.prefSending = {}
        m.prefTask.mode = "preferences"
    end if
    m.prefTask.control = "RUN"
end sub

sub onPreferences()
    data = m.prefTask.result
    oldUnseen = m.unseen
    m.prefs = mergePreferences(data, m.prefPending)
    m.prefSending = {}
    m.unseen = m.prefs.unseen
    storePreferences()
    if oldUnseen <> m.unseen then
        m.listKey = ""
        m.awardKey = ""
        if m.feed <> invalid and m.screen = "home" then
            buildCards()
            m.hint.text = homeHint()
        end if
    end if
    if m.prefPending.Count() > 0 then m.savePrefsTimer.control = "start"
end sub

sub onPreferencesError()
    m.prefPending = mergePreferences(m.prefSending, m.prefPending)
    m.prefSending = {}
    storePreferences()
end sub

function rowPreferences() as object
    id = m.feed.rows[m.rowIndex].id
    if m.prefs.lists.DoesExist(id) then return m.prefs.lists[id]
    return {}
end function

sub saveRowPreferences(values as object)
    if m.feed = invalid then return
    id = m.feed.rows[m.rowIndex].id
    if id = "search" then return
    patch = { lists: {} }
    patch.lists[id] = values
    queuePreferences(patch)
end sub

sub saveOptions()
    saveRowPreferences(m.opts)
end sub

sub rememberPosition()
    if m.restoringPosition or m.feed = invalid then return
    if m.screen = "list" then
        i = m.grid.itemFocused
        if i >= 0 and i < m.view.Count() then saveRowPreferences({ focus_id: m.view[i].id })
    else if m.screen = "awards" then
        values = { award_year: m.shownYear }
        f = m.awardRows.rowItemFocused
        if f <> invalid and f.Count() = 2 then
            if f[0] >= 0 and f[0] < m.awardView.Count() then
                if f[1] >= 0 and f[1] < m.awardView[f[0]].Count() then values.focus_id = m.awardView[f[0]][f[1]].id
            end if
        end if
        saveRowPreferences(values)
    end if
end sub

sub flushPreferences()
    refreshPreferences()
end sub

sub openConnection()
    dialog = CreateObject("roSGNode", "Dialog")
    dialog.title = "Conexão"
    dialog.message = "Verificando o computador e o Roku..."
    dialog.buttons = ["Reconectar", "Fechar"]
    dialog.observeField("buttonSelected", "onConnectionButton")
    m.connectionDialog = dialog
    m.top.dialog = dialog
    reconnectDevices()
end sub

sub onConnectionButton()
    if m.connectionDialog.buttonSelected = 0 then
        m.connectionDialog.message = "Procurando o computador e o Roku..."
        reconnectDevices()
    else
        m.connectionDialog.close = true
    end if
end sub

sub reconnectDevices()
    if m.connectionTask <> invalid then
        if m.connectionTask.state = "run" then return
    end if
    m.connectionTask = CreateObject("roSGNode", "ApiTask")
    m.connectionTask.mode = "connection"
    m.connectionTask.observeField("result", "onConnection")
    m.connectionTask.observeField("error", "onConnectionError")
    m.connectionTask.control = "RUN"
end sub

sub onConnection()
    c = m.connectionTask.result
    roku = "Roku sem conexão"
    if c.roku.connected then roku = "Roku conectado"
    text = "Computador conectado: " + c.computer.url + Chr(10) + roku
    if c.data.running then
        text = text + Chr(10) + "Dados: atualização em andamento"
        if c.data.total > 0 then text = text + " (" + c.data.done.ToStr() + "/" + c.data.total.ToStr() + ")"
    else if c.data.outcome = "failed" or c.data.last_result.outcome = "failed" then
        text = text + Chr(10) + "Dados: a última atualização falhou"
    else if c.data.last_result.outcome = "partial" then
        text = text + Chr(10) + "Dados: parte das fontes não atualizou"
    else if c.data.pending_offers <> invalid and c.data.pending_offers > 0 then
        text = text + Chr(10) + "Dados: " + c.data.pending_offers.ToStr() + " títulos aguardando consulta"
    else if c.data.incomplete then
        text = text + Chr(10) + "Dados: atualização ainda não confirmada"
    else
        stamp = c.data.synced_label
        text = text + Chr(10) + "Dados: " + stamp
    end if
    for each problem in c.data.last_result.problems
        text = text + Chr(10) + problem
    end for
    m.connectionDialog.message = text
    startFeed(false)
    refreshPreferences()
end sub

sub onConnectionError()
    m.connectionDialog.message = m.connectionTask.error + Chr(10) + "Mostrando os dados guardados quando disponíveis."
end sub
