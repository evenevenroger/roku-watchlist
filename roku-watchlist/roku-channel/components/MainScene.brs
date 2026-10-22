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
    m.seens = ["Vistos e não vistos", "Só os que não vi"]     ' "visto" = tem nota sua no IMDb
    resetOptions()

    m.home.observeField("itemSelected", "onHomeSelected")
    m.grid.observeField("itemSelected", "onGridSelected")
    m.grid.observeField("itemFocused", "onGridFocused")
    m.years.observeField("itemFocused", "onYearFocused")
    m.yearTimer = m.top.findNode("yearTimer")
    m.yearTimer.observeField("fire", "onYearTimer")
    m.listKey = ""       ' lista e filtros que estão montados na grade (voltar não remonta)
    m.awardKey = ""      ' idem para a tela de prêmios
    m.listSubtitle = ""
    m.view = []
    m.yearList = []
    m.awardView = []
    m.shownYear = ""
    m.awardRows.observeField("rowItemFocused", "onAwardFocused")
    m.awardRows.observeField("rowItemSelected", "onAwardSelected")
    m.optCats.observeField("itemSelected", "onCatSelected")
    m.optVals.observeField("itemSelected", "onValSelected")
    m.dButtons.observeField("buttonSelected", "onButtonSelected")

    m.loaded = {}          ' listas já carregadas nesta sessão (id -> true)
    m.rowLoading = ""      ' lista sendo carregada agora
    m.nextRow = ""         ' cartão escolhido enquanto outra lista carregava
    m.posterQueue = []     ' capas a guardar no Roku
    m.posterQueued = {}
    m.posterQueued.SetModeCaseSensitive()
    m.posterTask = invalid
    m.posterCache = {}     ' capas já guardadas (os códigos diferenciam maiúsculas)
    m.posterCache.SetModeCaseSensitive()
    ' o Roku só deixa ler pastas fora da tela (roFileSystem trava a abertura do canal aqui)
    m.listTask = CreateObject("roSGNode", "ApiTask")
    m.listTask.observeField("result", "onPosterList")
    m.listTask.mode = "posterlist"
    m.listTask.control = "RUN"

    m.offline = false
    m.pendingFeed = invalid
    m.cachedDone = false
    m.feedSame = false
    m.cachedTask = CreateObject("roSGNode", "ApiTask")
    m.cachedTask.observeField("result", "onCached")
    m.cachedTask.observeField("error", "onCachedError")
    m.cachedTask.mode = "cached"
    m.cachedTask.control = "RUN"
    startFeed(false)
end sub

' full = true: pede o feed inteiro mesmo que a cópia guardada pareça atual
sub startFeed(full as boolean)
    m.feedTask = CreateObject("roSGNode", "ApiTask")
    m.feedTask.observeField("result", "onFeed")
    m.feedTask.observeField("error", "onFeedError")
    m.feedTask.mode = "feed"
    m.feedTask.body = { full: full }
    m.feedTask.control = "RUN"
end sub

sub resetOptions()
    m.opts = { sort: 0, lang: "", service: "", genre: "", director: "", kind: 0, dur: 0, seen: 0, acat: "", ayear: "", ares: 0 }
end sub

' ---------- carregamento ----------

sub onCached()
    ' a cópia guardada só vale enquanto os dados novos não chegaram
    m.cachedDone = true
    if m.feed = invalid then applyFeed(m.cachedTask.result)
end sub

sub onCachedError()
    m.cachedDone = true
    if m.feed = invalid and m.feedSame then startFeed(true)    ' o PC disse "igual", mas a cópia não abriu
end sub

sub onFeedError()
    if m.feed = invalid then
        m.message.text = m.feedTask.error + Chr(10) + "Aperte OK para tentar de novo."
        return
    end if
    m.offline = true
    if m.screen = "home" then showHome()
end sub

sub onFeed()
    m.offline = false
    data = m.feedTask.result
    if data = invalid then return
    if data.DoesExist("same") then
        ' nada mudou desde a cópia guardada: não precisa montar tudo de novo
        if m.feed <> invalid then
            if m.screen = "home" then showHome()
        else if m.cachedDone then
            startFeed(true)
        else
            m.feedSame = true
        end if
        return
    end if
    if m.feed = invalid or m.screen = "home" or m.screen = "loading" then
        applyFeed(data)
    else
        m.pendingFeed = data     ' aplica quando voltar para a tela inicial
    end if
end sub

' Tela inicial: só os cartões (nome, quantidades, 3 capas e a versão de cada lista).
' Os filmes de cada lista chegam quando você entra nela (loadRow).
sub applyFeed(data as object)
    m.feed = data
    m.feed.details = {}
    m.loaded = {}
    m.listKey = ""
    m.awardKey = ""
    if m.feed.rows.Count() = 0 then
        m.home.content = CreateObject("roSGNode", "ContentNode")
        m.message.text = "Nenhum título das suas listas está nos seus serviços."
        m.message.visible = true
        return
    end if
    root = CreateObject("roSGNode", "ContentNode")
    for each row in m.feed.rows
        card = root.createChild("ContentNode")
        card.title = row.name
        if row.id = "new" then
            card.ShortDescriptionLine1 = row.count.ToStr() + " títulos nas últimas 3 semanas"
        else if row.id = "recent" then
            card.ShortDescriptionLine1 = row.count.ToStr() + " títulos que você abriu pelo canal"
        else
            card.ShortDescriptionLine1 = row.count.ToStr() + " para assistir agora  ·  " + row.total.ToStr() + " na lista"
        end if
        ' capas do cartão: as 3 maiores notas IMDb (novidades e vistos: as 3 mais recentes)
        card.HDPosterUrl = coverAt(row.covers, 0)
        card.SDPosterUrl = coverAt(row.covers, 1)
        card.FHDPosterUrl = coverAt(row.covers, 2)
        webs = []
        for i = 0 to 2
            code = ""
            if row.covers <> invalid and row.covers.Count() > i then code = row.covers[i]
            webs.Push(posterWeb(code))
        end for
        card.addFields({ webs: webs })
    end for
    keep = m.home.itemFocused
    m.home.content = root
    if keep > 0 and keep < root.getChildCount() then m.home.jumpToItem = keep
    m.message.visible = false
    flushPosters()
    showHome()
end sub

function coverAt(covers as dynamic, i as integer) as string
    if covers = invalid or covers.Count() <= i then return ""
    return posterUri(covers[i])
end function

' Textos que o servidor não repete e o endereço da capa (guardada no Roku, se já tiver).
sub prepItems(items as object)
    for each it in items
        it.genres = it.genreList.Join(", ")
        it.directors = it.directorList.Join(", ")
        it.sortTitle = LCase(it.title)
        if it.strips = invalid then it.strips = []
        it.posterWeb = posterWeb(it.poster)
        it.poster = posterUri(it.poster)
    end for
end sub

' Capa guardada no Roku se já existir; senão a da internet, e entra na fila para guardar.
function posterUri(code as string) as string
    if code = "" or Left(code, 4) = "http" then return code
    key = code.Replace("@", "_")
    if m.posterCache.DoesExist(key) then return posterFile(code)
    if not m.posterQueued.DoesExist(key) then
        m.posterQueued[key] = true
        m.posterQueue.Push(code)
    end if
    return posterWeb(code)
end function

' Capas já guardadas de aberturas anteriores; as que forem pedidas antes disso
' só vêm da internet nesta vez (a tarefa de capas vê que já existem e não baixa de novo).
sub onPosterList()
    names = m.listTask.result.names
    if names = invalid then return
    for each name in names
        if Right(name, 4) = ".jpg" then m.posterCache[Left(name, Len(name) - 4)] = true
    end for
end sub

sub flushPosters()
    if m.posterTask <> invalid or m.posterQueue.Count() = 0 then return
    m.posterTask = CreateObject("roSGNode", "ApiTask")
    m.posterTask.observeField("result", "onPostersSaved")
    m.posterTask.mode = "posters"
    m.posterTask.body = { codes: m.posterQueue }
    m.posterQueue = []
    m.posterTask.control = "RUN"
end sub

sub onPostersSaved()
    r = m.posterTask.result
    for each code in r.codes
        m.posterCache[code.Replace("@", "_")] = true
    end for
    if r.left <> invalid then m.posterQueue.Append(r.left)
    m.posterTask = invalid
    flushPosters()
end sub

' Linha de status da tela inicial: quando os dados foram atualizados e se algo falhou.
function statusText() as string
    st = m.feed.status
    parts = []
    if m.offline then
        parts.Push("Sem conexão com o computador: mostrando os dados guardados")
    end if
    if st <> invalid then
        if st.synced <> "" then parts.Push("Atualizado em " + st.synced)
        if st.incomplete = true then parts.Push("ainda consultando alguns títulos")
        if st.error <> "" then parts.Push("Última atualização falhou: " + st.error)
    end if
    return parts.Join("   ·   ")
end function

' ---------- tela inicial ----------

sub showHome()
    if m.pendingFeed <> invalid then
        data = m.pendingFeed
        m.pendingFeed = invalid
        applyFeed(data)
        return
    end if
    removeSearchRow()
    m.screen = "home"
    m.header.text = "Minha Watchlist"
    m.subtitle.text = statusText()
    m.hint.text = "*  buscar"
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
    row = m.feed.rows[m.rowIndex]
    if m.loaded.DoesExist(row.id) then
        openRow()
    else
        startRowLoad(row)
    end if
end sub

sub startRowLoad(row as object)
    if m.rowLoading <> "" then
        m.nextRow = row.id        ' abre este quando o carregamento atual terminar
        return
    end if
    m.nextRow = "" 
    m.rowLoading = row.id
    m.subtitle.text = "Abrindo " + row.name + "..."
    m.rowTask = CreateObject("roSGNode", "ApiTask")
    m.rowTask.observeField("result", "onRowLoaded")
    m.rowTask.observeField("error", "onRowError")
    m.rowTask.mode = "row"
    m.rowTask.body = { id: row.id, v: row.v }
    m.rowTask.control = "RUN"
end sub

sub onRowLoaded()
    data = m.rowTask.result
    id = m.rowLoading
    m.rowLoading = ""
    idx = -1
    for i = 0 to m.feed.rows.Count() - 1
        if m.feed.rows[i].id = id then idx = i
    end for
    if idx < 0 then return
    row = m.feed.rows[idx]
    items = data.row.items
    prepItems(items)
    row.items = items
    for each k in ["totals", "cats", "icon"]
        if data.row.DoesExist(k) then row[k] = data.row[k]
    end for
    for each k in data.details
        m.feed.details[k] = data.details[k]
    end for
    if data.v = row.v then m.loaded[id] = true     ' cópia de outra versão: recarrega na próxima vez
    flushPosters()
    if m.screen <> "home" then return
    m.subtitle.text = statusText()
    if m.nextRow <> "" and m.nextRow <> id then
        nxt = m.nextRow
        m.nextRow = ""
        for i = 0 to m.feed.rows.Count() - 1
            if m.feed.rows[i].id = nxt then
                m.rowIndex = i
                if m.loaded.DoesExist(nxt) then
                    openRow()
                else
                    startRowLoad(m.feed.rows[i])
                end if
                return
            end if
        end for
        return
    end if
    m.rowIndex = idx
    openRow()
end sub

sub onRowError()
    m.rowLoading = ""
    m.nextRow = ""
    m.subtitle.text = m.rowTask.error
end sub

sub openRow()
    resetOptions()
    ' padrão: maior nota do IMDb primeiro (novidades seguem da mais recente para a mais antiga)
    rid = m.feed.rows[m.rowIndex].id
    if rid <> "new" and rid <> "recent" then m.opts.sort = 1
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
    if m.listKey = m.rowIndex.ToStr() + FormatJson(m.opts) then
        m.header.text = m.feed.rows[m.rowIndex].name
        m.subtitle.text = m.listSubtitle
        m.message.visible = (m.view.Count() = 0)
        i = m.grid.itemFocused
        if i >= 0 and i < m.view.Count() then showFocusInfo(m.view[i])
    else
        rebuildView()
    end if
    m.grid.setFocus(true)
end sub

function passes(it as object) as boolean
    o = m.opts
    if o.lang <> "" and it.lang <> o.lang then return false
    if o.service <> "" and not contains(it.services, o.service) then return false
    if o.genre <> "" and not contains(it.genreList, o.genre) then return false
    if o.seen = 1 and it.mine > 0 then return false
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
        addPosterNode(root, it, line, it.strips)
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
    m.listSubtitle = m.subtitle.text
    m.listKey = m.rowIndex.ToStr() + FormatJson(m.opts)
end sub

function activeFilters() as string
    o = m.opts
    f = []
    if o.lang <> "" then f.Push(o.lang)
    if o.service <> "" then f.Push(o.service)
    if o.genre <> "" then f.Push(o.genre)
    if o.kind > 0 then f.Push(m.kinds[o.kind])
    if o.dur > 0 then f.Push(m.durs[o.dur])
    if o.seen > 0 then f.Push(m.seens[o.seen])
    if o.director <> "" then f.Push(o.director)
    if o.acat <> "" then f.Push(o.acat)
    if o.ayear <> "" then f.Push(o.ayear)
    if o.ares > 0 then f.Push(m.results[o.ares])
    return f.Join(", ")
end function

' Um pôster: capa, notas e a faixa do prêmio (strip = { t, w, i }).
' Tarjas de um pôster nas fileiras de prêmio: a do prêmio da fileira primeiro (first),
' depois as de outros festivais em que o filme venceu, sem repetir o ícone skipIcon.
function awardStrips(first as dynamic, it as object, skipIcon as string) as object
    s = []
    if first <> invalid then s.Push(first)
    for each x in it.strips
        if s.Count() < 2 and x.w = true and x.i <> skipIcon then s.Push(x)
    end for
    return s
end function

sub addPosterNode(parent as object, it as object, line as string, strips as object)
    node = parent.createChild("ContentNode")
    node.title = it.title
    node.HDPosterUrl = it.poster
    node.ShortDescriptionLine1 = it.rating
    node.addFields({ posterWeb: it.posterWeb })
    node.ShortDescriptionLine2 = line
    mineText = ""
    if it.mine > 0 then mineText = "Eu " + it.mine.ToStr()
    f = { mineText: mineText, rtC: it.rtC, rtA: it.rtA, stripText: "", stripWon: false, stripIcon: "", strip2Text: "", strip2Won: false, strip2Icon: "" }
    if strips.Count() > 0 then
        f.stripText = strips[0].t
        f.stripWon = strips[0].w
        f.stripIcon = strips[0].i
    end if
    if strips.Count() > 1 then
        f.strip2Text = strips[1].t
        f.strip2Won = strips[1].w
        f.strip2Icon = strips[1].i
    end if
    node.addFields(f)
end sub

sub onGridFocused()
    i = m.grid.itemFocused
    if i >= 0 and i < m.view.Count() then showFocusInfo(m.view[i])
end sub

' Faixa acima da grade: só o que NÃO aparece no pôster (título, notas, serviço e
' prêmio já estão lá): direção, duração, gêneros e idioma. Prêmios nunca vão aqui.
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
    keys.Append(["seen", "lang", "service", "genre", "director", "kind", "dur", "clear"])
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
        seen: "Mostrar:  " + m.seens[o.seen],
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
    else if m.cat = "seen" then
        m.panelTitle.text = "Mostrar"
        fixed = m.seens
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
    m.dPoster.uri = it.posterWeb.Replace("UX220", "UX500")
    m.dTitle.text = it.title
    meta = []
    if it.year <> "" then meta.Push(it.year)
    if it.runtime > 0 then meta.Push(formatRuntime(it.runtime))
    if it.rating <> "" then meta.Push("IMDb " + it.rating)
    if it.mine > 0 then meta.Push("Minha nota " + it.mine.ToStr())
    if it.rtC <> "" or it.rtA <> "" then meta.Push(rtText(it))
    m.dMeta.text = meta.Join("   ·   ")
    d = m.feed.details[it.id]
    if d = invalid then d = { plot: "", cast: "", awardText: "", country: "", play: [] }
    m.currentDetails = d
    info = []
    if it.directors <> "" then info.Push("Direção: " + it.directors)
    info.Push(it.lang)
    if d.country <> "" then info.Push(d.country)
    m.dInfo.text = info.Join("   ·   ")
    extra = []
    if it.genres <> "" then extra.Push(it.genres)
    if d.cast <> "" then extra.Push("Com " + d.cast)
    m.dGenres.text = extra.Join("   ·   ")
    m.dAwards.text = d.awardText
    m.dPlot.text = d.plot
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
    steps = invalid
    idx = m.dButtons.buttonSelected
    if m.currentDetails.play <> invalid and idx < m.currentDetails.play.Count() then steps = m.currentDetails.play[idx]
    m.playTask.body = { id: m.current.id, service: service, steps: steps }
    m.playCtx = { id: m.current.id, title: m.current.title, direct: (m.current.direct[idx] = true) }
    m.playTask.control = "RUN"
end sub

sub onPlayResult()
    r = m.playTask.result
    ctx = m.playCtx
    ' a ficha mudou enquanto o PC respondia: o aviso não é deste título
    if ctx = invalid or m.current = invalid or m.current.id <> ctx.id then return
    if r.ok = true then
        if r.local = true then
            m.dStatus.text = "Abrindo direto pelo Roku (o computador não respondeu)..."
        else if ctx.direct then
            m.dStatus.text = "Abrindo... (alguns serviços levam até 30 segundos)"
        else
            m.dStatus.text = "Abrindo o app. Procure por: " + ctx.title
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
    if m.feed = invalid and key = "OK" and m.feedTask.state <> "run" then
        m.message.text = "Tentando de novo..."
        startFeed(false)
        return true
    end if
    if m.screen = "home" and key = "options" and m.feed <> invalid then
        openSearch()
        return true
    end if
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
    if m.awardKey = m.rowIndex.ToStr() and m.yearList.Count() > 0 then
        m.years.visible = true
        m.yearsLine.visible = true
        m.awardRows.visible = true
        m.message.visible = false
        f = m.awardRows.rowItemFocused
        if f <> invalid and f.Count() = 2 and f[0] < m.awardView.Count() and f[1] < m.awardView[f[0]].Count() then showFocusInfo(m.awardView[f[0]][f[1]])
        m.years.setFocus(true)
        return
    end if
    m.awardKey = m.rowIndex.ToStr()

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

' Passando rápido pelos anos, só monta as fileiras do ano em que o cursor parar.
sub onYearFocused()
    if m.screen <> "awards" then return
    m.yearTimer.control = "stop"
    m.yearTimer.control = "start"
end sub

sub onYearTimer()
    i = m.years.itemFocused
    if m.screen = "awards" and i >= 0 and i < m.yearList.Count() and m.yearList[i].y <> m.shownYear then buildAwardRows(m.yearList[i].y)
end sub

' Oscar: uma fileira por categoria, vencedor primeiro. Cannes: uma fileira com os premiados do ano.
sub buildAwardRows(year as string)
    m.shownYear = year
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
                    ' venceu nesta categoria: "Venceu" e os outros festivais; senão, os prêmios que ganhou
                    if p.won = 1 then
                        strips = awardStrips({ t: "Venceu", w: true, i: "trophy" }, p.it, "trophy")
                    else
                        strips = awardStrips(invalid, p.it, "")
                    end if
                    addPosterNode(rowNode, p.it, p.it.year + "  ·  " + p.it.services.Join(" · "), strips)
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
            addPosterNode(rowNode, p.it, p.it.year + "  ·  " + p.it.services.Join(" · "), awardStrips({ t: p.c, w: true, i: row.icon }, p.it, row.icon))
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


' ---------- busca (botão * na tela inicial) ----------

sub openSearch()
    kd = CreateObject("roSGNode", "StandardKeyboardDialog")
    kd.title = "Buscar título"
    kd.message = ["Busca em todas as listas, pelo título em português ou original."]
    kd.buttons = ["Buscar", "Cancelar"]
    kd.observeField("buttonSelected", "onSearchButton")
    m.searchDialog = kd
    m.top.dialog = kd
end sub

sub onSearchButton()
    kd = m.searchDialog
    q = ""
    if kd.buttonSelected = 0 then q = LCase(kd.text).Trim()
    kd.close = true
    if q = "" then return
    m.searchQ = q
    m.subtitle.text = "Buscando " + Chr(34) + q + Chr(34) + "..."
    m.searchTask = CreateObject("roSGNode", "ApiTask")
    m.searchTask.observeField("result", "onSearchResult")
    m.searchTask.observeField("error", "onSearchError")
    m.searchTask.mode = "search"
    m.searchTask.body = { q: q }
    m.searchTask.control = "RUN"
end sub

sub onSearchResult()
    data = m.searchTask.result
    items = data.items
    prepItems(items)
    for each k in data.details
        m.feed.details[k] = data.details[k]
    end for
    flushPosters()
    showSearch(items)
end sub

' Sem o PC: procura só nas listas que já foram abertas nesta sessão.
sub onSearchError()
    q = m.searchQ
    results = []
    seen = {}
    for each row in m.feed.rows
        if row.id <> "search" and row.items <> invalid then
            for each it in row.items
                if not seen.DoesExist(it.id) and (Instr(1, it.sortTitle, q) > 0 or Instr(1, it.orig, q) > 0) then
                    seen[it.id] = true
                    copy = {}
                    copy.Append(it)
                    copy.pos = results.Count()
                    results.Push(copy)
                end if
            end for
        end if
    end for
    showSearch(results)
end sub

sub showSearch(results as object)
    q = m.searchQ
    if m.screen <> "home" then return
    m.subtitle.text = statusText()
    removeSearchRow()
    m.feed.rows.Push({ id: "search", name: "Busca: " + q, total: results.Count(), award: false, items: results })
    m.listKey = ""
    m.rowIndex = m.feed.rows.Count() - 1
    resetOptions()
    m.opts.sort = 1
    showList()
    if results.Count() = 0 then m.message.text = "Nada encontrado para " + Chr(34) + q + Chr(34) + "."
end sub

sub removeSearchRow()
    if m.feed = invalid then return
    n = m.feed.rows.Count()
    if n > 0 and m.feed.rows[n - 1].id = "search" then m.feed.rows.Delete(n - 1)
end sub
