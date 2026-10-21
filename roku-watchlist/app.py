"""Watchlist → Roku.

Lê as listas do IMDb, descobre onde cada título está nos seus streamings
(JustWatch, Brasil), junta notas do Rotten Tomatoes e prêmios (Oscar, Cannes)
e manda o Roku abrir o título no app certo. O código fica no pacote watchlist/.

Uso:  python app.py     (ou IniciarOculto.vbs, sem janela)
"""
from watchlist.server import main

if __name__ == "__main__":
    main()
