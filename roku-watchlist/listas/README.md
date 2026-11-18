# Listas que não estão no IMDb

Cada arquivo `listas/<nome>.json` vira uma lista do app quando o `config.json` tem uma entrada com o id
`local:<nome>` (a posição no `config.json` é a posição no app). O arquivo traz os títulos na ordem da
lista, cada um com o código do IMDb:

```json
{"name": "...", "source": "https://...", "items": [{"pos": 1, "title": "...", "year": 1931, "imdb": "tt0022080"}]}
```

| Arquivo | Origem | Atualização |
|---|---|---|
| `abraccine.json` | Wikipedia (pt): 100 melhores filmes brasileiros segundo a Abraccine, 2016 | fixa |
| `rotten100.json` | Wikipedia (en): filmes com 100% no Rotten Tomatoes | a cada seis meses (1º de maio e 1º de novembro) |
| `ofcs_scifi.json` | Online Film Critics Society: Top 100 Sci-Fi Films, 2002 (ofcs.org) | fixa |
| `ofcs_overlooked90s.json` | Online Film Critics Society: Top 100 Overlooked Films of the 1990s, 2004 (ofcs.org; sem anos, *Hamlet* é o de Branagh, 1996) | fixa |

## Atualização semestral do `rotten100.json`

A tarefa agendada "Atualizar lista 100% Rotten Tomatoes" do Claude faz isto; para fazer à mão, na pasta
`roku-watchlist`:

1. `python tools/atualizar_rotten100.py --teste` mostra os filmes que entram (`+`), saem (`-`) e os que
   ficaram sem código do IMDb (`?`).
2. `python tools/atualizar_rotten100.py` grava o arquivo. Filmes que já estavam mantêm o código, inclusive
   os corrigidos à mão.
3. Para cada `?`, buscar o filme no IMDb (título, ano e diretor da página da Wikipedia) e acrescentar ao
   arquivo com o **mesmo título e ano da Wikipedia**, assim as próximas rodadas reaproveitam o código.
   Rodar o passo 2 de novo para pôr o filme na posição certa.
4. Pedir uma sincronização ao servidor (`POST http://localhost:8790/api/sync`); os filmes novos ganham os
   serviços de streaming em alguns minutos.
5. `python -m unittest discover -s tests -q`, commit e push.

Correções feitas à mão na importação de 17/11/2026, que o script preserva: *Earth: One Amazing Day*
(tt6238896, a busca caía em *Earth*, de 2007), *Hilda* (2014, de Andrés Clariond), *Stray Dog* (2014, de
Debra Granik), *Uncertain* (2015), *The Prince of Nothingwood* (IMDb: *Nothingwood*), *King Cohen*, os dois
*A Bread Factory*, *The Oscar Nominated Short Films 2018: Animation* e *Anima* (2019, de Paul Thomas
Anderson). *Apocalypse Now: Final Cut* aponta para o *Apocalypse Now* de 1979, porque o IMDb não tem página
própria para a versão.
