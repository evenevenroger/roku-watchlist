' Telas: "home" (cartões das listas) → "list" (grade com ordenar/filtrar) → ficha.

sub init()
    m.header = m.top.findNode("header")
    m.subtitle = m.top.findNode("subtitle")
    m.hint = m.top.findNode("hint")
    m.message = m.top.findNode("message")
    m.home = m.top.findNode("home")
    m.grid = m.top.findNode("grid")
    m.years = m.top.findNode("years")
    m.yearsLine = m.top.findNode("yearsLine")
    m.awardRows = m.top.findNode("awardRows")
    m.focusInfo = m.top.findNode("focusInfo")
    m.panel = m.top.findNode("panel")
    m.panelTitle = m.top.findNode("panelTitle")
    m.optCats = m.top.findNode("optCats")
    m.optVals = m.top.findNode("optVals")
    m.details = m.top.findNode("details")
    m.dPoster = m.top.findNode("dPoster")
    m.dTitle = m.top.findNode("dTitle")
    m.dMeta = m.top.findNode("dMeta")
    m.dInfo = m.top.findNode("dInfo")
    m.dGenres = m.top.findNode("dGenres")
    m.dAwards = m.top.findNode("dAwards")
    m.dPlot = m.top.findNode("dPlot")
    m.dButtons = m.top.findNode("dButtons")
    m.dStatus = m.top.findNode("dStatus")

    m.feed = invalid
    m.rowIndex = 0
    m.view = []
    m.current = invalid
    m.screen = "loading"
    m.sorts = [
        { label: "Ordem da lista", field: "pos", flags: "" },
        { label: "Nota IMDb", field: "r", flags: "r" },
        { label: "Minha nota", field: "mine", flags: "r" },
        { label: "Idioma", field: "lang", flags: "" },
        { label: "Mais recentes", field: "y", flags: "r" },
        { label: "Mais antigos", field: "y", flags: "" },
        { label: "Mais curtos", field: "rtSort", flags: "" },
        { label: "Título (A-Z)", field: "sortTitle", flags: "" },
        { label: "Ano do prêmio", field: "ay", flags: "r" }
    ]
    m.results = ["Indicados e vencedores", "Só vencedores", "Só indicados"]
    m.kinds = ["Filmes e séries", "Só filmes", "Só séries"]
    m.durs = ["Qualquer duração", "Até 1h40", "Até 2h", "Mais de 2h"]
    resetOptions()

    m.home.observeField("itemSelected", "onHomeSelected")
    m.grid.observeField("itemSelected", "onGridSelected")
    m.grid.observeField("itemFocused", "onGridFocused")
    m.years.observeField("itemFocused", "onYearFocused")
    m.awardRows.observeField("rowItemFocused", "onAwardFocused")
    m.awardRows.observeField("rowItemSelected", "onAwardSelected")
    m.optCats.observeField("itemSelected", "onCatSelected")
    m.optVals.observeField("itemSelected", "onValSelected")
    m.dButtons.observeField("buttonSelected", "onButtonSelected")

    m.feedTask = CreateObject("roSGNode", "ApiTask")
    m.feedTask.observeField("result", "onFeed")
    m.feedTask.observeField("error", "onFeedError")
    m.feedTask.mode = "feed"
    m.feedTask.control = "RUN"
end sub

sub resetOptions()
    m.opts = { sort: 0, lang: "", service: "", genre: "", director: "", kind: 0, dur: 0, acat: "", ayear: "", ares: 0 }
end sub

' ---------- carregamento ----------

sub onFeedError()
    m.message.text = m.feedTask.error
end sub

sub onFeed()
    m.feed = m.feedTask.result
    if m.feed.rows.Count() = 0 then
        m.message.text = "Nenhum título das suas listas está nos seus serviços."
        return
    end if
    root = CreateObject("roSGNode", "ContentNode")
    for each row in m.feed.rows
        card = root.createChild("ContentNode")
        card.title = row.name
        card.ShortDescriptionLine1 = row.items.Count().ToStr() + " para assistir agora  ·  " + row.total.ToStr() + " na lista"
        card.HDPosterUrl = posterAt(row.items, 0)
        card.SDPosterUrl = posterAt(row.items, 1)
        card.FHDPosterUrl = posterAt(row.items, 2)
    end for
    m.home.content = root
    m.message.visible = false
    showHome()
end sub

function posterAt(items as object, i as integer) as string
    if items.Count() > i then return items[i].poster
    return ""
end function

' ---------- tela inicial ----------

sub showHome()
    m.screen = "home"
    m.header.text = "Minha Watchlist"
    m.subtitle.text = "Escolha uma lista"
    m.hint.text = ""
    m.grid.visible = false
    m.focusInfo.visible = false
    m.panel.visible = false
    m.years.visible = false
    m.yearsLine.visible = false
    m.awardRows.visible = false
    m.message.visible = false
    m.home.visible = true
    m.home.setFocus(true)
end sub

sub onHomeSelected()
    m.rowIndex = m.home.itemSelected
    resetOptions()
    if m.feed.rows[m.rowIndex].award = true then
        showAwards()
    else
        showList()
    end if
end sub

' ---------- tela da lista ----------

sub showList()
    m.screen = "list"
    m.home.visible = false
    m.grid.visible = true
    m.focusInfo.visible = true
    m.hint.text = "*  ordenar e filtrar      Play  sortear"
    rebuildView()
    m.grid.setFocus(true)
end sub

function passes(it as object) as boolean
    o = m.opts
    if o.lang <> "" and it.lang <> o.lang then return false
    if o.service <> "" and not contains(it.services, o.service) then return false
    if o.genre <> "" and not contains(it.genreList, o.genre) then return false
    if o.kind = 1 and it.series then return false
    if o.kind = 2 and not it.series then return false
    if o.dur = 1 and (it.runtime = 0 or it.runtime > 100) then return false
    if o.dur = 2 and (it.runtime = 0 or it.runtime > 120) then return false
    if o.dur = 3 and it.runtime <= 120 then return false
    if o.director <> "" and not contains(it.directorList, o.director) then return false
    if o.acat <> "" or o.ayear <> "" or o.ares > 0 then
        ok = false
        for each a in it.aw
            if (o.acat = "" or a.c = o.acat) and (o.ayear = "" or a.y = o.ayear) and (o.ares = 0 or (o.ares = 1 and a.w) or (o.ares = 2 and not a.w)) then ok = true
        end for
        if not ok then return false
    end if
    return true
end function

function contains(arr as object, value as string) as boolean
    for each v in arr
        if v = value then return true
    end for
    return false
end function

sub rebuildView()
    row = m.feed.rows[m.rowIndex]
    view = []
    for each it in row.items
        if passes(it) then view.Push(it)
    end for
    s = m.sorts[m.opts.sort]
    if s.field = "lang" then
        view.SortBy("r", "r")      ' dentro de cada idioma, melhor nota primeiro
        view.SortBy("lang")
    else if s.field = "mine" then
        view.SortBy("r", "r")
        view.SortBy("mine", "r")
    else if s.field <> "pos" then
        view.SortBy(s.field, s.flags)
    end if
    m.view = view

    root = CreateObject("roSGNode", "ContentNode")
    for each it in view
        ' sempre: ano e serviços; nas ordens por idioma/duração, isso vem antes
        line = it.services.Join(" · ")
        if it.year <> "" then line = it.year + "  ·  " + line
        if s.field = "lang" then
            line = it.lang + "  ·  " + line
        else if s.field = "rtSort" and it.runtime > 0 then
            line = formatRuntime(it.runtime) + "  ·  " + line
        end if
        addPosterNode(root, it, line, it.strip)
    end for
    m.grid.content = root
    if view.Count() > 0 then
        m.grid.jumpToItem = 0
        showFocusInfo(view[0])
    else
        m.focusInfo.text = ""
    end if

    m.header.text = row.name
    parts = [view.Count().ToStr() + " de " + row.items.Count().ToStr() + " títulos", "Ordem: " + s.label]
    f = activeFilters()
    if f <> "" then parts.Push(f)
    m.subtitle.text = parts.Join("   ·   ")
    m.message.visible = (view.Count() = 0)
    if view.Count() = 0 then m.message.text = "Nada com esses filtros. Aperte * para mudar."
end sub

function activeFilters() as string
    o = m.opts
    f = []
    if o.lang <> "" then f.Push(o.lang)
    if o.service <> "" then f.Push(o.service)
    if o.genre <> "" then f.Push(o.genre)
    if o.kind > 0 then f.Push(m.kinds[o.kind])
    if o.dur > 0 then f.Push(m.durs[o.dur])
    if o.director <> "" then f.Push(o.director)
    if o.acat <> "" then f.Push(o.acat)
    if o.ayear <> "" then f.Push(o.ayear)
    if o.ares > 0 then f.Push(m.results[o.ares])
    return f.Join(", ")
end function

' Um pôster: capa, notas e a faixa do prêmio (strip = { t, w, i }).
sub addPosterNode(parent as object, it as object, line as string, strip as object)
    node = parent.createChild("ContentNode")
    node.title = it.title
    node.HDPosterUrl = it.poster
    node.ShortDescriptionLine1 = it.rating
    node.ShortDescriptionLine2 = line
    mineText = ""
    if it.mine > 0 then mineText = "Eu " + it.mine.ToStr()
    node.addFields({ mineText: mineText, rtC: it.rtC, rtA: it.rtA, stripText: strip.t, stripWon: strip.w, stripIcon: strip.i })
end sub

sub onGridFocused()
    i = m.grid.itemFocused
    if i >= 0 and i < m.view.Count() then showFocusInfo(m.view[i])
end sub

' Faixa acima da grade: só o que NÃO aparece no pôster (título, notas, serviço e
' prêmio da lista já estão lá): direção, duração, gêneros, idioma e outros prêmios.
sub showFocusInfo(it as object)
    parts = []
    if it.directors <> "" then parts.Push("Direção: " + it.directors)
    if it.runtime > 0 then parts.Push(formatRuntime(it.runtime))
    genres = []
    for each g in it.genreList
        if genres.Count() < 3 then genres.Push(g)
    end for
    if genres.Count() > 0 then parts.Push(genres.Join(", "))
    parts.Push(it.lang)
    if it.awardOtherText <> "" then parts.Push(it.awardOtherText)
    m.focusInfo.text = parts.Join("   ·   ")
end sub

function rtText(it as object) as string
    t = []
    if it.rtC <> "" then t.Push("RT crítica " + it.rtC + "%")
    if it.rtA <> "" then t.Push("público " + it.rtA + "%")
    return t.Join(" / ")
end function

sub onGridSelected()
    showDetails(m.view[m.grid.itemSelected])
end sub

sub pickRandom()
    if m.view.Count() = 0 then return
    showDetails(m.view[Rnd(m.view.Count()) - 1])
end sub

' ---------- painel de ordenar e filtrar ----------

sub openPanel()
    m.panel.visible = true
    m.optVals.visible = false
    m.optCats.visible = true
    m.panelTitle.text = "Ordenar e filtrar"
    fillList(m.optCats, catLabels())
    m.optCats.setFocus(true)
end sub

' Itens do painel; as listas de prêmio ganham categoria, ano e resultado.
function catKeys() as object
    keys = ["sort"]
    if m.feed.rows[m.rowIndex].award = true then keys.Append(["acat", "ayear", "ares"])
    keys.Append(["lang", "service", "genre", "director", "kind", "dur", "clear"])
    return keys
end function

function catLabels() as object
    o = m.opts
    names = {
        sort: "Ordenar por:  " + m.sorts[o.sort].label,
        acat: "Categoria:  " + iif(o.acat, "Todas"),
        ayear: "Ano:  " + iif(o.ayear, "Todos"),
        ares: "Resultado:  " + m.results[o.ares],
        lang: "Idioma:  " + iif(o.lang, "Todos"),
        service: "Serviço:  " + iif(o.service, "Todos"),
        genre: "Gênero:  " + iif(o.genre, "Todos"),
        director: "Diretor:  " + iif(o.director, "Todos"),
        kind: "Tipo:  " + m.kinds[o.kind],
        dur: "Duração:  " + m.durs[o.dur],
        clear: "Limpar filtros"
    }
    labels = []
    for each k in catKeys()
        labels.Push(names[k])
    end for
    return labels
end function

function iif(value as string, fallback as string) as string
    if value = "" then return fallback
    return value
end function

sub fillList(list as object, labels as object)
    root = CreateObject("roSGNode", "ContentNode")
    for each l in labels
        n = root.createChild("ContentNode")
        n.title = l
    end for
    list.content = root
end sub

sub onCatSelected()
    keys = catKeys()
    m.cat = keys[m.optCats.itemSelected]
    if m.cat = "clear" then
        keepSort = m.opts.sort
        resetOptions()
        m.opts.sort = keepSort
        rebuildView()
        fillList(m.optCats, catLabels())
        return
    end if
    m.choices = []
    labels = []
    fixed = invalid
    if m.cat = "sort" then
        m.panelTitle.text = "Ordenar por"
        fixed = []
        for each srt in m.sorts
            fixed.Push(srt.label)
        end for
    else if m.cat = "kind" then
        m.panelTitle.text = "Tipo"
        fixed = m.kinds
    else if m.cat = "dur" then
        m.panelTitle.text = "Duração"
        fixed = m.durs
    else if m.cat = "ares" then
        m.panelTitle.text = "Resultado"
        fixed = m.results
    end if
    if fixed <> invalid then
        for i = 0 to fixed.Count() - 1
            m.choices.Push(i)
            labels.Push(fixed[i])
        end for
    else
        titles = { lang: "Idioma", service: "Serviço", genre: "Gênero", director: "Diretor", acat: "Categoria", ayear: "Ano" }
        m.panelTitle.text = titles[m.cat]
        counts = valueCounts(m.cat)
        m.choices.Push("")
        labels.Push("Todos")
        for each c in counts
            m.choices.Push(c.value)
            labels.Push(c.value + "  (" + c.n.ToStr() + ")")
        end for
    end if
    fillList(m.optVals, labels)
    m.optCats.visible = false
    m.optVals.visible = true
    m.optVals.jumpToItem = 0
    m.optVals.setFocus(true)
end sub

' Valores presentes na lista atual, do mais comum para o menos comum
' (anos: do mais recente para o mais antigo).
function valueCounts(key as string) as object
    tally = {}
    tally.SetModeCaseSensitive()
    for each it in m.feed.rows[m.rowIndex].items
        if key = "acat" or key = "ayear" then
            seen = {}
            for each a in it.aw
                v = a.c
                if key = "ayear" then v = a.y
                if v <> "" and not seen.DoesExist(v) then
                    seen[v] = true
                    addCount(tally, v)
                end if
            end for
        else
            field = key
            if key = "service" then field = "services"
            if key = "genre" then field = "genreList"
            if key = "director" then field = "directorList"
            v = it[field]
            if type(v) = "roArray" then
                for each x in v
                    addCount(tally, x)
                end for
            else
                addCount(tally, v)
            end if
        end if
    end for
    out = []
    for each k in tally
        out.Push({ value: k, n: tally[k] })
    end for
    if key = "ayear" then
        out.SortBy("value", "r")
    else
        out.SortBy("value")
        out.SortBy("n", "r")
    end if
    return out
end function

sub addCount(tally as object, key as string)
    if tally.DoesExist(key) then
        tally[key] = tally[key] + 1
    else
        tally[key] = 1
    end if
end sub

sub onValSelected()
    m.opts[m.cat] = m.choices[m.optVals.itemSelected]
    rebuildView()
    closePanel()
end sub

sub backToCats()
    m.optVals.visible = false
    m.optCats.visible = true
    m.panelTitle.text = "Ordenar e filtrar"
    fillList(m.optCats, catLabels())
    m.optCats.setFocus(true)
end sub

sub closePanel()
    m.panel.visible = false
    m.grid.setFocus(true)
end sub

' ---------- ficha ----------

sub showDetails(it as object)
    m.current = it
    m.dPoster.uri = it.poster.Replace("UX300", "UX500")
    m.dTitle.text = it.title
    meta = []
    if it.year <> "" then meta.Push(it.year)
    if it.runtime > 0 then meta.Push(formatRuntime(it.runtime))
    if it.rating <> "" then meta.Push("IMDb " + it.rating)
    if it.mine > 0 then meta.Push("Minha nota " + it.mine.ToStr())
    if it.rtC <> "" or it.rtA <> "" then meta.Push(rtText(it))
    m.dMeta.text = meta.Join("   ·   ")
    info = []
    if it.directors <> "" then info.Push("Direção: " + it.directors)
    info.Push(it.lang)
    if it.country <> "" then info.Push(it.country)
    m.dInfo.text = info.Join("   ·   ")
    extra = []
    if it.genres <> "" then extra.Push(it.genres)
    if it.cast <> "" then extra.Push("Com " + it.cast)
    m.dGenres.text = extra.Join("   ·   ")
    m.dAwards.text = it.awardText
    m.dPlot.text = it.plot
    labels = []
    for i = 0 to it.services.Count() - 1
        if it.direct[i] then
            labels.Push("Assistir no " + it.services[i])
        else
            labels.Push("Abrir o " + it.services[i] + " (buscar lá)")
        end if
    end for
    m.dButtons.buttons = labels
    m.dStatus.text = ""
    m.details.visible = true
    m.dButtons.setFocus(true)
end sub

function formatRuntime(minutes as integer) as string
    h = Int(minutes / 60)
    mm = minutes - h * 60
    if h = 0 then return mm.ToStr() + " min"
    if mm < 10 then return h.ToStr() + "h0" + mm.ToStr()
    return h.ToStr() + "h" + mm.ToStr()
end function

sub hideDetails()
    m.details.visible = false
    if m.screen = "awards" then
        m.awardRows.setFocus(true)
        return
    end if
    m.grid.setFocus(true)
end sub

sub onButtonSelected()
    if m.current = invalid then return
    service = m.current.services[m.dButtons.buttonSelected]
    m.dStatus.text = "Abrindo no " + service + "..."
    m.playTask = CreateObject("roSGNode", "ApiTask")
    m.playTask.observeField("result", "onPlayResult")
    m.playTask.observeField("error", "onPlayError")
    m.playTask.mode = "play"
    m.playTask.body = { id: m.current.id, service: service }
    m.playTask.control = "RUN"
end sub

sub onPlayResult()
    r = m.playTask.result
    if r.ok = true then
        if m.current.direct[m.dButtons.buttonSelected] then
            m.dStatus.text = "Abrindo... (alguns serviços levam até 30 segundos)"
        else
            m.dStatus.text = "Abrindo o app. Procure por: " + m.current.title
        end if
    else
        m.dStatus.text = "Não deu certo: " + r.error
    end if
end sub

sub onPlayError()
    m.dStatus.text = m.playTask.error
end sub

' ---------- controle remoto ----------

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if m.details.visible then
        if key = "back" then
            hideDetails()
            return true
        end if
        return false
    end if
    if m.panel.visible then
        if key = "back" or key = "options" then
            if m.optVals.visible and key = "back" then
                backToCats()
            else
                closePanel()
            end if
            return true
        end if
        return false
    end if
    if m.screen = "awards" then
        if key = "back" then
            showHome()
            return true
        else if key = "right" and m.years.hasFocus() then
            m.awardRows.setFocus(true)
            return true
        else if key = "left" and m.awardRows.isInFocusChain() then
            m.years.setFocus(true)
            return true
        else if key = "play" then
            pickRandomAward()
            return true
        end if
        return false
    end if
    if m.screen = "list" then
        if key = "back" then
            showHome()
            return true
        else if key = "options" then
            openPanel()
            return true
        else if key = "play" then
            pickRandom()
            return true
        end if
    end if
    return false
end function

' ---------- Oscar e Cannes: anos à esquerda, fileiras à direita ----------

sub showAwards()
    m.screen = "awards"
    row = m.feed.rows[m.rowIndex]
    m.home.visible = false
    m.grid.visible = false
    m.header.text = row.name
    m.subtitle.text = ""
    m.hint.text = "<  >  anos e filmes      Play  sortear"
    m.focusInfo.visible = true
    m.focusInfo.text = ""

    ' anos que têm algum filme nos seus serviços, com a quantidade
    counts = {}
    for each it in row.items
        seen = {}
        for each a in it.aw
            if a.y <> "" and not seen.DoesExist(a.y) then
                seen[a.y] = true
                addCount(counts, a.y)
            end if
        end for
    end for
    m.yearList = []
    for each y in counts
        m.yearList.Push({ y: y, n: counts[y] })
    end for
    m.yearList.SortBy("y", "r")
    labels = []
    for each e in m.yearList
        labels.Push(e.y + "     " + e.n.ToStr())
    end for
    fillList(m.years, labels)
    m.years.visible = true
    m.yearsLine.visible = true
    m.awardRows.visible = true
    if m.yearList.Count() = 0 then
        m.message.visible = true
        m.message.text = "Nenhum filme desta lista está nos seus serviços."
        return
    end if
    m.message.visible = false
    m.years.jumpToItem = 0
    buildAwardRows(m.yearList[0].y)
    m.years.setFocus(true)
end sub

sub onYearFocused()
    i = m.years.itemFocused
    if m.screen = "awards" and i >= 0 and i < m.yearList.Count() then buildAwardRows(m.yearList[i].y)
end sub

' Oscar: uma fileira por categoria, vencedor primeiro. Cannes: uma fileira com os premiados do ano.
sub buildAwardRows(year as string)
    row = m.feed.rows[m.rowIndex]
    isOscar = (row.id = "award:oscar")
    m.awardView = []
    root = CreateObject("roSGNode", "ContentNode")
    if isOscar then
        for each cat in row.cats
            picked = []
            for each it in row.items
                for each a in it.aw
                    if a.y = year and a.c = cat then
                        won = 0
                        if a.w then won = 1
                        picked.Push({ it: it, won: won, r: it.r })
                    end if
                end for
            end for
            if picked.Count() > 0 then
                picked.SortBy("r", "r")
                picked.SortBy("won", "r")
                total = row.totals[year + "|" + cat]
                if total = invalid then total = picked.Count()
                rowNode = root.createChild("ContentNode")
                rowNode.title = cat + "      " + picked.Count().ToStr() + " de " + total.ToStr() + " indicados nos seus serviços"
                items = []
                for each p in picked
                    strip = { t: "", w: false, i: "" }
                    if p.won = 1 then strip = { t: "Venceu", w: true, i: "trophy" }
                    addPosterNode(rowNode, p.it, p.it.year + "  ·  " + p.it.services.Join(" · "), strip)
                    items.Push(p.it)
                end for
                m.awardView.Push(items)
            end if
        end for
    else
        picked = []
        total = 0
        for each cat in row.cats
            t = row.totals[year + "|" + cat]
            if t <> invalid then total = total + t
            for each it in row.items
                for each a in it.aw
                    if a.y = year and a.c = cat then picked.Push({ it: it, c: cat })
                end for
            end for
        end for
        rowNode = root.createChild("ContentNode")
        rowNode.title = row.name + " " + year + "      " + picked.Count().ToStr() + " de " + total.ToStr() + " premiados nos seus serviços"
        items = []
        for each p in picked
            addPosterNode(rowNode, p.it, p.it.year + "  ·  " + p.it.services.Join(" · "), { t: p.c, w: true, i: "palm" })
            items.Push(p.it)
        end for
        m.awardView.Push(items)
    end if
    m.awardRows.content = root
    if m.awardView.Count() > 0 and m.awardView[0].Count() > 0 then showFocusInfo(m.awardView[0][0])
end sub

sub onAwardFocused()
    f = m.awardRows.rowItemFocused
    if f = invalid or f.Count() < 2 then return
    if f[0] < m.awardView.Count() and f[1] < m.awardView[f[0]].Count() then showFocusInfo(m.awardView[f[0]][f[1]])
end sub

sub onAwardSelected()
    s = m.awardRows.rowItemSelected
    showDetails(m.awardView[s[0]][s[1]])
end sub

sub pickRandomAward()
    all = []
    for each r in m.awardView
        all.Append(r)
    end for
    if all.Count() > 0 then showDetails(all[Rnd(all.Count()) - 1])
end sub
