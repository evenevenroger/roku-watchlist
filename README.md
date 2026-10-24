# Minha Watchlist → Roku

Aplicativo pessoal para reunir listas públicas do IMDb, consultar a disponibilidade no Brasil e abrir filmes ou séries nos aplicativos de streaming do Roku. A interface web funciona no computador e no celular conectado à mesma rede.

## Recursos

- Listas do IMDb, notas pessoais, categorias de premiações e disponibilidade por serviço.
- Busca, ordenação, filtros e posição compartilhados entre navegador e Roku.
- Títulos e pôsteres de filmes em inglês, com os nomes original e português na ficha. Produções brasileiras e portuguesas conservam o nome em português.
- Tarjas de premiação para filmes e séries, com prioridade entre Emmy, Golden Globe, BAFTA, Critics’ Choice e Peabody nas séries.
- Filtro pela duração total das séries. Totais com episódios sem duração usam uma estimativa identificada por `~`.
- Diagnóstico de conexão, progresso da sincronização, salvamento da fila e retomada após interrupções.
- Geração do ZIP do canal com o endereço do servidor da rede local.

## Executar no Windows

Requer Python 3.12 ou superior. O ambiente usado no desenvolvimento é Python 3.14. Node.js é opcional, para os testes da interface e a validação do canal.

Na raiz deste repositório:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r roku-watchlist/requirements.txt
Copy-Item roku-watchlist/config.example.json roku-watchlist/config.json
```

Edite `roku-watchlist/config.json` com o seu identificador do IMDb (`imdb_user`), o IP do Roku (`roku_ip`) e os serviços que você utiliza. O identificador aparece no endereço do perfil IMDb, no formato `ur...`. As listas precisam estar públicas. `auto_lists` permite descobrir automaticamente as listas públicas do perfil.

```powershell
.\.venv\Scripts\python.exe roku-watchlist/app.py
```

Abra `http://localhost:8790` no computador. No celular, use o endereço local do computador na porta 8790. O painel **Conexão** mostra esse endereço e o estado do Roku e dos dados.

O servidor é destinado à rede doméstica. O código no GitHub permite instalar o aplicativo; o computador executa o servidor que conversa com o Roku.

## Canal Roku

1. Ative o modo de desenvolvedor do seu Roku.
2. Com o servidor rodando, abra **Conexão → Baixar canal para o Roku**, ou baixe `http://localhost:8790/roku-channel.zip`.
3. Instale o ZIP pelo instalador de desenvolvedor do Roku, usando a senha configurada no aparelho.

O ZIP contém o endereço do computador. Se o endereço mudar, o canal tenta localizar o servidor novamente na rede. As credenciais do instalador são fornecidas ao instalar e não fazem parte do repositório.

## Início automático

`Iniciar.bat`, `IniciarOculto.vbs`, `ensure_server.py` e `ConfigurarInicioAutomatico.ps1` auxiliam a execução no Windows. Os lançadores silenciosos e a tarefa agendada foram configurados para `C:\Python314`; ajuste o caminho do interpretador se a sua instalação estiver em outro local.

O script PowerShell cria uma tarefa para iniciar o servidor ao entrar no Windows e verificar a cada minuto se ele precisa ser religado.

## Configuração e dados locais

`config.example.json` é um modelo. O arquivo pessoal `config.json`, o diretório `data/`, os ZIPs gerados, ambientes virtuais e relatórios locais de manutenção são ignorados pelo Git. O diretório `data/` é criado durante o uso e guarda consultas, preferências, fila de sincronização e logs.

`offers_max_age_days` define a janela de atualização da disponibilidade; o padrão é três dias. A sincronização percorre toda a fila mantendo um intervalo entre consultas, salva o progresso e interrompe consultas seguintes quando uma fonte falha. A tela distingue uma fila pendente de uma falha de fonte.

IMDb, JustWatch, Rotten Tomatoes, os aplicativos de streaming e seus endereços podem mudar. Uma consulta de disponibilidade reflete a informação devolvida pela fonte naquele momento. O código usa endpoints de terceiros e destina-se ao uso pessoal, observadas as condições das respectivas fontes.

## Verificações

Na pasta `roku-watchlist`, com as dependências instaladas:

```powershell
python -m unittest discover -s tests -q
node --test tests/test_ui.cjs
npx --yes brighterscript@0.73.8 --root-dir roku-channel --create-package false --copy-to-staging false
```

Os testes usam fontes simuladas e servidores locais descartáveis. Os scripts de arte em `tools/` são opcionais; a geração de imagens requer Pillow.

## Organização

```text
roku-watchlist/
  app.py                 Entrada do servidor
  config.example.json    Modelo de configuração
  requirements.txt       Dependências Python
  watchlist/             Fontes, sincronização, API e integração com o Roku
  static/index.html      Interface para computador e celular
  roku-channel/          Canal SceneGraph/BrightScript
  tests/                 Testes Python e JavaScript
  tools/                 Geração dos recursos visuais
```
