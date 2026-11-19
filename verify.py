#!/usr/bin/env python3
"""Verificação do índice de dashboards (index.html).

Roda em Playwright sobre o arquivo local e falha (exit 1) se:
  - o nº de cards renderizados não bate com o nº de itens do JSON embutido;
  - a busca devolve mais de um card por termo de teste (regressão de 18/11/2026:
    .card{display:flex} vencia o atributo [hidden] e a busca não filtrava);
  - o estado "sem resultado" não aparece quando nada casa;
  - os chips de categoria contam errado;
  - há pageerror;
  - há overflow horizontal em 320/390/768/1280 px.

Uso: python3 verify.py
"""
import json
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
URL = (HERE / "index.html").as_uri()

VISIVEIS = ("() => [...document.querySelectorAll('a.card')]"
            ".filter(e => e.getClientRects().length > 0).map(e => e.dataset.n)")

# termo -> único projeto que deve sobrar
BUSCAS = {
    "cointeligencia": "cointeligencia",
    "cointeligência": "cointeligencia",
    "marco civil": "mci-dashboard",
    "nvidia": "nvidia-3tri-2026",
    "lindb": "lindb-dashboard",
    "licitações": "l14133-dashboard",
    "kissinger": "sobre-a-china",
}

falhas = []


def checa(cond, msg):
    print(("  ok   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def main():
    html = (HERE / "index.html").read_text(encoding="utf-8")
    dados = json.loads(re.search(r'<script id="dados" type="application/json">(.*?)</script>',
                                 html, re.S).group(1))
    total = len(dados["itens"])
    cats = {}
    for it in dados["itens"]:
        cats[it["cat"]] = cats.get(it["cat"], 0) + 1

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(500)

        print(f"catálogo: {total} painéis em {len(cats)} assuntos")
        checa(len(pg.evaluate(VISIVEIS)) == total,
              f"todos os {total} cards renderizam na abertura")

        for termo, esperado in BUSCAS.items():
            pg.fill("#q", termo)
            pg.wait_for_timeout(300)
            vis = pg.evaluate(VISIVEIS)
            checa(vis == [esperado], f"busca '{termo}' devolve só {esperado} (obtido: {vis})")

        pg.fill("#q", "zzzqqq")
        pg.wait_for_timeout(300)
        checa(pg.locator("#empty").is_visible() and not pg.evaluate(VISIVEIS),
              "estado 'sem resultado' aparece e nenhum card fica à vista")

        pg.fill("#q", "")
        pg.wait_for_timeout(300)
        for cat in ("MPPE", "Legislação", "Livros", "Economia"):
            pg.get_by_role("tab", name=cat).click()
            pg.wait_for_timeout(300)
            n = len(pg.evaluate(VISIVEIS))
            checa(n == cats.get({"MPPE": "mppe", "Legislação": "lei",
                                 "Livros": "livro", "Economia": "economia"}[cat]),
                  f"chip {cat} mostra {n} cards")
        pg.get_by_role("tab", name="Todos").click()
        pg.wait_for_timeout(300)
        checa(len(pg.evaluate(VISIVEIS)) == total, "volta a Todos com o catálogo inteiro")

        for w in (320, 390, 768, 1280):
            pg.set_viewport_size({"width": w, "height": 900})
            pg.wait_for_timeout(250)
            larg = pg.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
            checa(larg[0] <= larg[1] + 1, f"sem overflow horizontal em {w}px ({larg[0]} ≤ {larg[1]})")

        checa(not erros, f"nenhum pageerror ({erros[:2]})")
        b.close()

    if falhas:
        print(f"\n{len(falhas)} falha(s)")
        sys.exit(1)
    print("\ntudo certo")


if __name__ == "__main__":
    main()
