#!/usr/bin/env python3
"""Gera o índice de dashboards Vercel (HTML autocontido) a partir da API do Vercel.

Fonte do inventário: GET /v9/projects + /v9/projects/{id}/domains (alias estável),
e o HTML ao vivo de cada alias para título real e detecção do gate de senha.

Uso:  python3 build.py            # usa cache local, se existir
      python3 build.py --refresh  # re-consulta a API e os 98 aliases
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "inventario.json")

# ---------------------------------------------------------------- catálogo
# (projeto Vercel, categoria, descrição curta)
# categoria: (título da seção, rótulo curto do chip)
CAT = {
    "mppe": ("MPPE e Judiciário", "MPPE"),
    "lei": ("Legislação navegável", "Legislação"),
    "juris": ("Jurisprudência e doutrina", "Jurisprudência"),
    "livro": ("Guias de livros e estudo", "Livros"),
    "economia": ("Economia, mercado e finanças", "Economia"),
    "politica": ("Política e eleições 2026", "Política"),
    "saude": ("Saúde", "Saúde"),
    "imprensa": ("Imprensa e dossiês", "Imprensa"),
    "tech": ("Tecnologia e ferramentas", "Tecnologia"),
    "pessoal": ("Vida pessoal e rotina", "Pessoal"),
}

ITENS = [
    # ---------------- MPPE
    ("correicoes-mppe", "mppe", "Registro de correições da CGMP/MPPE"),
    ("dashboard-processos-sim-2026", "mppe", "Painel de processos do Conselho Superior (SIM)"),
    ("procuradoria-civel", "mppe", "Movimentação de processos da Procuradoria Cível"),
    ("procuradoria-civel-estatisticas", "mppe", "Estatísticas da Procuradoria de Justiça Cível"),
    ("procuradoria-caruaru-civel", "mppe", "Estatísticas da PJ Regional de Caruaru · Cível"),
    ("procuradoria-caruaru-criminal", "mppe", "Estatísticas da PJ Regional de Caruaru · Criminal"),
    ("distribuicao-caruaru", "mppe", "Distribuição de processos em Caruaru · ago/2026"),
    ("djen-lote3-caruaru", "mppe", "Achados do DJEN — lote de 30/10, 32 ações"),
    ("caruaru-ementas", "mppe", "72 ementas da Câmara Regional de Caruaru"),
    ("pronunciamentos-civel", "mppe", "1.278 ementas CNJ com busca semântica"),
    ("quadro-membros-mppe", "mppe", "Quadro geral: cargos, vagas e circunscrições"),
    ("mppe-cargos-atribuicoes", "mppe", "486 cargos de 1º grau e suas atribuições"),
    ("circunscricoes-ministeriais-mppe", "mppe", "Mapa das circunscrições ministeriais de PE"),
    ("habitacao-urbanismo-mppe", "mppe", "Cargos com atuação em habitação e urbanismo"),
    ("recorte-cjf-mppe", "mppe", "Promotorias abaixo da mediana de movimentação"),
    ("movimentacoes-carreira-mppe", "mppe", "Promoções, remoções e movimentações de carreira"),
    ("antiguidade-2inst-analise", "mppe", "Antiguidade do 2º grau, lista analisada"),
    ("mppe-idade-procuradores", "mppe", "Idade dos Procuradores de Justiça"),
    ("mppe-designacoes-cgmp-ativas", "mppe", "Designações por membro · CGMP 2023–2026"),
    ("vitaliciamento-csmp-2109", "mppe", "Vitaliciamento · sessão do CSMP de 21/09"),
    ("csmp-votos-2026", "mppe", "Votos da sessão do CSMP de 04/11/2026"),
    ("cpj-2a-sessao-2026", "mppe", "2ª Sessão do CPJ, com os 5 painéis embutidos"),
    ("gaju-mps-2026", "mppe", "GAJU/GECJAO nos Ministérios Públicos — Brasil 2026"),
    ("papj-estudo-qualitativo", "mppe", "Estudo qualitativo do PAPJ (oficina AMPEO)"),
    ("item8-correicoes-pjdc-cidadania", "mppe", "Correições PJDC Caruaru e Jaboatão · item 8"),
    ("cnmp-processos-mppe", "mppe", "Processos do MP/PE em tramitação no CNMP (ELO)"),
    ("resolucao-residencia-mppe-2026", "mppe", "Minuta da resolução de residência na comarca"),
    ("membros-fora-titularidade-2026", "mppe", "117 membros que residem fora da comarca de titularidade (excl. RMR) · com distância em km"),
    ("mppe-transparencia-guia", "mppe", "Guia do Portal da Transparência do MPPE"),
    ("camara-regional-caruaru", "mppe", "Circunscrições judiciárias do TJPE em Caruaru"),
    ("tjpe-circunscricoes-judiciarias", "mppe", "Atlas das comarcas e termos do TJPE"),
    # ---------------- Legislação
    ("vade-mecum-digital", "lei", "Índice-mãe dos 8 painéis de lei · 4.153 dispositivos"),
    ("cf-dashboard", "lei", "CF/1988 + ADCT artigo a artigo · 425 dispositivos"),
    ("constituicao-e-o-supremo", "lei", "CF/88 anotada pelo STF · 8.888 julgados por artigo"),
    ("cc-dashboard", "lei", "Código Civil navegável · 2.083 dispositivos"),
    ("cpc-dashboard", "lei", "CPC navegável · 1.074 dispositivos"),
    ("cdc-dashboard", "lei", "CDC 8.078/1990 artigo a artigo"),
    ("eca-dashboard", "lei", "ECA 8.069/1990 · 329 dispositivos"),
    ("lacp-dashboard", "lei", "Lei de Ação Civil Pública 7.347/1985"),
    ("alimentos-dashboard", "lei", "Lei de Alimentos 5.478/1968"),
    ("l9656-dashboard", "lei", "Lei dos Planos de Saúde 9.656/1998"),
    ("ms-dashboard", "lei", "Mandado de Segurança 12.016/2009"),
    ("improbidade-dashboard", "lei", "Lei de Improbidade Administrativa 8.429/1992"),
    ("ritjpe-dashboard", "lei", "Regimento Interno do TJPE navegável"),
    ("ritjpe-titulo-vi-julgamento", "lei", "RITJPE, Título VI — Do Julgamento, artigo a artigo"),
    # ---------------- Jurisprudência
    ("ementario-cnmp", "juris", "Ementário do Conselho Nacional do Ministério Público"),
    ("ementario-cgmp-rs", "juris", "Ementário da Corregedoria-Geral do MP do RS"),
    ("temas-stj-saude", "juris", "Temas repetitivos do STJ sobre saúde e planos"),
    ("adi-6606-teto-remuneratorio", "juris", "ADI 6606 — teto constitucional e remuneração"),
    ("analise-sentenca-sulamerica-2026", "juris", "Análise da sentença da ACP SulAmérica (34ª Vara Cível)"),
    ("proporcional-razoavel", "juris", "Virgílio Afonso da Silva, capítulo a capítulo"),
    ("relevancia-questao-federal", "juris", "Relevância da questão federal no REsp"),
    # ---------------- Guias de livros
    ("gramsci-coutinho", "livro", "Gramsci: um estudo sobre seu pensamento político"),
    ("kant-metafisica-costumes", "livro", "A Metafísica dos Costumes, de Kant"),
    ("condicao-humana", "livro", "A Condição Humana, de Hannah Arendt"),
    ("huntington-choque-civilizacoes", "livro", "O Choque das Civilizações, de Huntington"),
    ("tao-da-fisica", "livro", "O Tao da Física, de Fritjof Capra"),
    ("lyra-promotoria-publica", "livro", "Teoria e Prática da Promotoria Pública"),
    ("manual-portugues-redacao-juridica", "livro", "Manual de Português e Redação Jurídica"),
    ("roteiro-construir-sertao", "livro", "Roteiro para construir no Sertão do Araripe"),
    ("guia-aristoteles", "livro", "Hub dos guias de Aristóteles"),
    ("guia-etica-nicomaco", "livro", "Ética a Nicômaco, guia interativo"),
    ("guia-politica", "livro", "Política, de Aristóteles"),
    ("guia-poetica", "livro", "Poética, de Aristóteles"),
    ("guia-metafisica", "livro", "Metafísica, de Aristóteles"),
    ("guia-sobre-a-alma", "livro", "Sobre a Alma (De Anima), de Aristóteles"),
    ("guia-organon", "livro", "Órganon, de Aristóteles"),
    # ---------------- Economia
    ("mercado-analitico", "economia", "Fechamento do pregão de 03/11 · 45 ativos, 8 classes"),
    ("carteira-acoes-2026", "economia", "As 33 empresas da carteira: topo, dia, alertas"),
    ("tesouro-direto-dashboard", "economia", "Cotações e títulos públicos do Tesouro Direto"),
    ("dashboard-long-short", "economia", "Operações long/short do dia, variação e calculadora"),
    ("eu-acuso-lara-resende", "economia", "O artigo de Lara Resende e a conta dos 7,5%"),
    ("fisher-resende-brazil", "economia", "Resposta de Cochrane: juros, dívida e o teste da teoria"),
    ("horta-tirania-dos-juros", "economia", "15 posts conferidos contra as séries do BCB e do BCE"),
    ("watchlist-ti-dashboard", "economia", "Watchlist de ações de tecnologia da informação"),
    # ---------------- Política
    ("pesquisas-2turno-2026", "politica", "Calendário das pesquisas do 2º turno presidencial"),
    ("abstencao-capitais-2026", "politica", "Abstenção nas capitais: 1º contra 2º turno"),
    ("abstencao-estados-2026", "politica", "Abstenção nos estados: 1º contra 2º turno"),
    ("secoes-alteradas-2turno-2026", "politica", "4.288 seções alteradas, com rota no Maps"),
    ("senado-eua-2026", "politica", "Eleição ao Senado dos EUA: mapa das 35 cadeiras"),
    ("carta-flavio-bolsonaro-2026", "politica", "A carta de Flávio Bolsonaro, transcrita em 3 páginas"),
    ("oqueestaemjogo-celular", "politica", "O que está em jogo na sua cidade, por CEP"),
    # ---------------- Saúde
    ("bioimpedancia-charles", "saude", "Composição corporal InBody 120 · 6 medições"),
    ("exames-joemia-2026", "saude", "Resultados de exames de Ana Joêmia · 25/08"),
    ("judicializacao-planos-saude", "saude", "Relatório 2026 da judicialização de planos de saúde"),
    ("guia-judicializacao-saude", "saude", "Guia interativo da judicialização da saúde"),
    ("ancora-judicializacao-saude", "saude", "Âncora do acervo audiovisual sobre judicialização"),
    # ---------------- Imprensa
    ("economist-ia-1710", "imprensa", "The Economist, edição de IA de 17/10/2026"),
    ("vestigios-da-noite", "imprensa", "Dossiê da piauí: 125 mensagens de Daniel Vorcaro"),
    # ---------------- Tecnologia
    ("pulwtop-mac-mini", "tech", "PULWTOP BD240A × BS212C, hubs para o Mac mini M4"),
    ("relatorio-hub-macmini-m4", "tech", "Hub USB contra dock Thunderbolt com SSD NVMe"),
    ("obsidian-guia-interativo", "tech", "Guia do Obsidian, do zero ao grafo"),
    ("hermes-bots-guide", "tech", "Guia dos bots do Hermes"),
    ("guia-teste", "tech", "Obra de teste — modelo de guia interativo"),
    # ---------------- Pessoal
    ("clima-pe", "pessoal", "Acompanhamento meteorológico de Pernambuco"),
    ("vault-chlima123", "pessoal", "Painel do vault chlima123"),
    ("vault-grapho-chlima123", "pessoal", "Grafo de notas do vault chlima123"),
    ("okinawa-vanekairi", "pessoal", "Caderno de viagem Okinawa — OMO5 Naha"),
    ("consolidado-supermercado", "pessoal", "Consolidado de preços de supermercado 2026"),
]


# títulos de reserva para painéis cujo <title> não é útil
TITULO_RESERVA = {
    "antiguidade-2inst-analise": "Antiguidade do 2º grau — análise",
}


# ---------------------------------------------------------------- inventário
def _token():
    env = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.strip().startswith("VERCEL_API_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return json.load(open(os.path.expanduser(
        "~/Library/Application Support/com.vercel.cli/auth.json")))["token"]


def _curl(url, token=None):
    cmd = ["curl", "-sL", "--max-time", "45", url]
    if token:
        cmd[1:1] = ["-H", f"Authorization: Bearer {token}"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def _api(path, token):
    return json.loads(_curl("https://api.vercel.com" + path, token))


def refresh():
    token = _token()
    projects, until = [], None
    while True:
        suffix = f"&until={until}" if until else ""
        d = _api(f"/v9/projects?limit=100{suffix}", token)
        projects += d.get("projects", [])
        until = (d.get("pagination") or {}).get("next")
        if not until:
            break

    def domains(p):
        d = _api(f"/v9/projects/{p['id']}/domains", token)
        host = [x["name"] for x in d.get("domains", [])
                if x["name"].endswith(".vercel.app") and not x.get("redirect")]
        return p["name"], host[0] if host else p["name"] + ".vercel.app"

    hosts = {}
    with ThreadPoolExecutor(8) as ex:
        for name, host in ex.map(domains, projects):
            hosts[name] = host

    def live(item):
        name, host = item
        body = _curl("https://" + host + "/")
        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        return name, {
            "host": host,
            "code": "200" if body else "0",
            "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
            "gate": bool(re.search(r"prompt\s*\(|pass\s*!==", body)),
        }

    inv = {}
    with ThreadPoolExecutor(10) as ex:
        for name, info in ex.map(live, hosts.items()):
            inv[name] = info
    json.dump(inv, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return inv


def inventario():
    if "--refresh" in sys.argv or not os.path.exists(CACHE):
        return refresh()
    return json.load(open(CACHE, encoding="utf-8"))


# ---------------------------------------------------------------- build
TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Índice de dashboards — Vercel</title>
<meta name="description" content="__TOTAL__ painéis estáticos publicados na conta Vercel, classificados por assunto.">
<style>
  :root{
    color-scheme: light dark;
    --bg:#f5f5f7;
    --bg-grad:radial-gradient(1200px 600px at 12% -8%, #eaf0ff 0%, transparent 60%),
               radial-gradient(900px 520px at 92% 0%, #f3eaff 0%, transparent 55%);
    --surface: rgba(255,255,255,.72);
    --surface-solid:#ffffff;
    --line: rgba(0,0,0,.08);
    --line-strong: rgba(0,0,0,.14);
    --ink:#101014;
    --ink-2:#3a3a42;
    --ink-3:#63636e;
    --accent:#0a63d6;
    --accent-ink:#0a4fa8;
    --chip: rgba(120,120,128,.10);
    --chip-ink:#4a4a54;
    --pill:#ffffff;
    --pill-shadow:0 1px 2px rgba(0,0,0,.10), 0 6px 18px rgba(0,0,0,.10);
    --card: rgba(255,255,255,.78);
    --card-hover: rgba(255,255,255,.95);
    --lock:#7a5200;
    --lock-bg: rgba(255,190,60,.20);
    --hairline: linear-gradient(180deg, rgba(0,0,0,.10), rgba(0,0,0,0));
    --bg-veil: rgba(245,245,247,.86);
    --radius:22px;
    --maxw:1120px;
    --spring:cubic-bezier(.22,1,.36,1);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --bg:#0b0b0d;
      --bg-grad:radial-gradient(1100px 560px at 10% -10%, #14203a 0%, transparent 62%),
                 radial-gradient(900px 500px at 95% 0%, #221636 0%, transparent 58%);
      --surface: rgba(22,22,26,.72);
      --surface-solid:#16161a;
      --line: rgba(255,255,255,.10);
      --line-strong: rgba(255,255,255,.18);
      --ink:#f4f4f7;
      --ink-2:#cfcfd7;
      --ink-3:#a1a1ad;
      --accent:#65a6ff;
      --accent-ink:#9cc6ff;
      --chip: rgba(235,235,245,.10);
      --chip-ink:#c9c9d3;
      --pill: #34343c;
      --pill-shadow:0 1px 2px rgba(0,0,0,.5), 0 8px 22px rgba(0,0,0,.45);
      --card: rgba(24,24,29,.72);
      --card-hover: rgba(34,34,41,.92);
      --lock:#f2c14e;
      --lock-bg: rgba(242,193,78,.16);
      --hairline: linear-gradient(180deg, rgba(255,255,255,.16), rgba(255,255,255,0));
      --bg-veil: rgba(11,11,13,.86);
    }
  }
  html[data-theme="light"]{ color-scheme: light; }
  html[data-theme="dark"]{
    color-scheme: dark;
    --bg:#0b0b0d;
    --bg-grad:radial-gradient(1100px 560px at 10% -10%, #14203a 0%, transparent 62%),
               radial-gradient(900px 500px at 95% 0%, #221636 0%, transparent 58%);
    --surface: rgba(22,22,26,.72);
    --surface-solid:#16161a;
    --line: rgba(255,255,255,.10);
    --line-strong: rgba(255,255,255,.18);
    --ink:#f4f4f7;
    --ink-2:#cfcfd7;
    --ink-3:#a1a1ad;
    --accent:#65a6ff;
    --accent-ink:#9cc6ff;
    --chip: rgba(235,235,245,.10);
    --chip-ink:#c9c9d3;
    --pill: #34343c;
    --pill-shadow:0 1px 2px rgba(0,0,0,.5), 0 8px 22px rgba(0,0,0,.45);
    --card: rgba(24,24,29,.72);
    --card-hover: rgba(34,34,41,.92);
    --lock:#f2c14e;
    --lock-bg: rgba(242,193,78,.16);
    --hairline: linear-gradient(180deg, rgba(255,255,255,.16), rgba(255,255,255,0));
    --bg-veil: rgba(11,11,13,.86);
  }

  *,*::before,*::after{ box-sizing:border-box; }
  html,body{ margin:0; }
  body{
    background: var(--bg);
    background-image: var(--bg-grad);
    background-attachment: fixed;
    color: var(--ink);
    font: 400 17px/1.5 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    min-height: 100vh;
  }
  .wrap{ max-width: var(--maxw); margin:0 auto; padding: 0 20px; }

  /* ---------- barra translúcida ---------- */
  .bar{
    position: sticky; top:0; z-index:50;
    background: var(--surface);
    -webkit-backdrop-filter: saturate(180%) blur(22px);
    backdrop-filter: saturate(180%) blur(22px);
    border-bottom: 1px solid var(--line);
  }
  @supports not ((backdrop-filter: blur(2px)) or (-webkit-backdrop-filter: blur(2px))){
    .bar{ background: var(--surface-solid); }
  }
  .bar-in{
    max-width: var(--maxw); margin:0 auto; padding: 10px 20px;
    display:flex; align-items:center; gap:14px;
  }
  .brand{
    display:flex; align-items:center; gap:10px;
    letter-spacing:-0.01em; font-weight:600; font-size:15px;
    color: var(--ink); text-decoration:none; white-space:nowrap;
  }
  .brand .dot{
    width:10px; height:10px; border-radius:50%;
    background: linear-gradient(160deg, #4f9dff, #0a63d6);
    box-shadow: 0 0 calc(0px) 0 rgba(10,99,214,.55);
    transition: box-shadow 220ms var(--spring);
  }
  .brand:hover .dot{ box-shadow: 0 0 0 5px rgba(10,99,214,.14); }

  .grow{ flex:1 1 auto; }

  .search{
    position:relative; display:flex; align-items:center;
    flex: 1 1 320px; max-width: 420px;
    background: var(--chip);
    border: 1px solid transparent;
    border-radius: 12px; height:38px; padding: 0 34px 0 34px;
    transition: border-color 160ms ease, background 160ms ease;
  }
  .search:focus-within{
    border-color: var(--accent);
    background: var(--surface-solid);
  }
  .search svg{ position:absolute; left:11px; width:15px; height:15px; color: var(--ink-3); }
  .search input{
    border:0; outline:0; background:transparent; width:100%;
    font: inherit; font-size:15px; color: var(--ink);
  }
  .search input::placeholder{ color: var(--ink-3); }
  .search kbd{
    position:absolute; right:8px; font: 500 11px/1 ui-monospace, monospace;
    color: var(--ink-3); background: var(--surface-solid);
    border:1px solid var(--line-strong); border-radius:6px; padding:4px 6px;
  }
  .search:focus-within kbd{ opacity:0; }

  .iconbtn{
    -webkit-appearance:none; appearance:none; cursor:pointer;
    width:38px; height:38px; flex:0 0 auto; border-radius:11px;
    border:1px solid var(--line); background: var(--chip);
    color: var(--ink-2);
    display:grid; place-items:center;
    transition: transform 120ms ease-out, background 160ms ease, border-color 160ms ease;
  }
  .iconbtn:hover{ border-color: var(--line-strong); color: var(--ink); }
  .iconbtn:active{ transform: scale(.94); }
  .iconbtn:focus-visible, .chip:focus-visible, .card:focus-visible, .search:focus-within{
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .iconbtn svg{ width:17px; height:17px; }

  /* ---------- cabeçalho ---------- */
  header.hero{ padding: 54px 20px 18px; max-width: var(--maxw); margin:0 auto; }
  .eyebrow{
    display:inline-flex; align-items:center; gap:8px;
    font-size:12.5px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
    color: var(--accent-ink);
  }
  .eyebrow .pip{ width:6px; height:6px; border-radius:50%; background: var(--accent); }
  h1{
    margin: 14px 0 0;
    font-size: clamp(2.1rem, 5.4vw, 3.5rem);
    line-height: 1.04;
    letter-spacing: -0.031em;
    font-weight: 700;
    font-optical-sizing: auto;
    max-width: 18ch;
  }
  .dek{
    margin: 16px 0 0; max-width: 62ch;
    font-size: clamp(1rem, 1.6vw, 1.06rem);
    line-height: 1.55; letter-spacing: -0.003em;
    color: var(--ink-2);
  }
  .stats{ display:flex; flex-wrap:wrap; gap: 10px 26px; margin-top: 24px; }
  .stat{ display:flex; flex-direction:column; gap:2px; }
  .stat b{ font-size: 22px; letter-spacing:-0.02em; font-variant-numeric: tabular-nums; }
  .stat span{ font-size: 12.5px; letter-spacing:.02em; color: var(--ink-3); text-transform:uppercase; font-weight:600; }

  /* ---------- chips ---------- */
  .chips-row{
    position: sticky; top: 59px; z-index: 40;
    background: var(--bg-veil);
    -webkit-backdrop-filter: saturate(160%) blur(16px);
    backdrop-filter: saturate(160%) blur(16px);
  }
  .chips-wrap{ max-width: var(--maxw); margin: 0 auto; padding: 10px 20px 12px; }
  .chips{
    position:relative; display:flex; gap:4px; overflow-x:auto; scrollbar-width:none;
    padding: 5px; border-radius:15px; background: var(--chip);
    -webkit-overflow-scrolling: touch;
  }
  .chips::-webkit-scrollbar{ display:none; }
  #pill{
    position:absolute; top:5px; left:0; height: calc(100% - 10px); width: 0;
    background: var(--pill); border-radius:11px; box-shadow: var(--pill-shadow);
    pointer-events:none; will-change: transform, width;
    transform-origin: center;
  }
  .chip{
    -webkit-appearance:none; appearance:none; cursor:pointer; position:relative; z-index:1;
    flex:0 0 auto; border:0; background:transparent; color: var(--chip-ink);
    font: 500 13.5px/1 inherit; letter-spacing:-0.008em;
    padding: 9px 11px; border-radius:11px; white-space:nowrap;
    transition: color 200ms ease, transform 110ms ease-out;
  }
  .chip:hover{ color: var(--ink); }
  .chip:active{ transform: scale(.97); }
  .chip[aria-selected="true"]{ color: var(--ink); font-weight:600; }
  .chip .n{
    margin-left:7px; font-size:11.5px; font-variant-numeric: tabular-nums;
    color: var(--ink-3); font-weight:500;
  }
  .chip[aria-selected="true"] .n{ color: var(--accent-ink); }

  /* ---------- seções e cards ---------- */
  main{ max-width: var(--maxw); margin: 0 auto; padding: 6px 20px 80px; }
  section.group{ margin-top: 40px; scroll-margin-top: 132px; }
  .group-head{ display:flex; align-items:baseline; gap:12px; margin-bottom: 14px; }
  .group-head h2{
    margin:0; font-size: 13px; font-weight:700; letter-spacing:.075em; text-transform:uppercase;
    color: var(--ink-3);
  }
  .group-head .rule{ flex:1 1 auto; height:1px; background: var(--line); }
  .group-head .count{
    font-size:12.5px; color: var(--ink-3); font-variant-numeric: tabular-nums;
  }
  .grid{
    display:grid; gap:12px;
    grid-template-columns: repeat(auto-fill, minmax(268px, 1fr));
  }
  .card{
    position:relative; display:flex; flex-direction:column; gap:7px;
    padding: 18px 18px 16px;
    border-radius: 18px;
    background: var(--card);
    border: 1px solid var(--line);
    -webkit-backdrop-filter: saturate(160%) blur(12px);
    backdrop-filter: saturate(160%) blur(12px);
    color: inherit; text-decoration: none;
    transform: translateZ(0);
    transition: transform 240ms var(--spring), box-shadow 240ms var(--spring),
                background 200ms ease, border-color 200ms ease, opacity 260ms ease;
    box-shadow: 0 1px 1px rgba(0,0,0,.04);
    will-change: transform;
  }
  .card:hover{
    transform: translateY(-3px);
    background: var(--card-hover);
    border-color: var(--line-strong);
    box-shadow: 0 10px 28px rgba(0,0,0,.10), 0 2px 6px rgba(0,0,0,.05);
  }
  .card:active{ transform: scale(.985); transition-duration: 90ms; }
  .card h3{
    margin:0; font-size: 16.5px; line-height:1.28; font-weight:600; letter-spacing:-0.017em;
    padding-right: 26px;
  }
  .card .lock ~ h3{ padding-right: 68px; }
  .card p{
    margin:0; font-size: 14px; line-height:1.42; color: var(--ink-2);
    letter-spacing: -0.002em;
  }
  .card .meta{
    margin-top: 4px; display:flex; align-items:center; gap:8px;
    font: 500 11.5px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--ink-3);
  }
  .card .meta .host{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .lock{
    position:absolute; top:14px; right:14px;
    display:inline-flex; align-items:center; gap:4px;
    height: 21px; padding: 0 7px 0 5px; border-radius: 7px;
    background: var(--lock-bg); color: var(--lock);
    font: 600 10.5px/1 -apple-system, system-ui, sans-serif; letter-spacing:.02em;
  }
  .lock svg{ width:10px; height:10px; }
  .card .arrow{
    margin-left:auto; color: var(--ink-3); opacity:0; transform: translateX(-4px);
    transition: opacity 200ms ease, transform 260ms var(--spring);
  }
  .card:hover .arrow{ opacity:1; transform: translateX(0); }
  .card .arrow svg{ width:13px; height:13px; }

  .empty{
    display:none; text-align:center; padding: 64px 20px; color: var(--ink-3);
  }
  .empty.show{ display:block; }
  .empty b{ display:block; color: var(--ink); font-size:18px; margin-bottom:6px; letter-spacing:-0.01em; }

  footer{
    max-width: var(--maxw); margin: 0 auto; padding: 26px 20px 60px;
    border-top: 1px solid var(--line);
    color: var(--ink-3); font-size: 13px; line-height:1.6;
  }
  footer a{ color: var(--accent-ink); text-decoration:none; }
  footer a:hover{ text-decoration:underline; }
  footer p{ margin: 0 0 6px; }

  /* entrada em cascata (não é gesto: easing é adequado aqui) */
  .card.enter{ animation: rise 420ms var(--spring) both; }
  @keyframes rise{ from{ opacity:0; transform: translateY(8px) scale(.995); } to{ opacity:1; transform:none; } }

  @media (max-width: 640px){
    .bar-in{ padding: 8px 14px; gap:10px; flex-wrap: nowrap; }
    .brand span.full{ display:none; }
    .search{ max-width:none; flex: 1 1 auto; }
    .search kbd{ display:none; }
    header.hero{ padding: 34px 16px 10px; }
    .chips-wrap{ padding: 8px 10px 10px; }
    main{ padding: 4px 16px 64px; }
    .chips-row{ top: 55px; }
    .grid{ grid-template-columns: 1fr; }
  }

  @media (prefers-reduced-motion: reduce){
    *{ animation-duration: 1ms !important; animation-iteration-count: 1 !important; }
    .card, .card:hover, .card:active{ transform:none !important; transition: opacity 180ms ease, background 180ms ease; }
    #pill{ transition: none; }
    .card .arrow{ display:none; }
  }
  @media (prefers-reduced-transparency: reduce){
    .bar, .card, .chips-wrap{ -webkit-backdrop-filter:none; backdrop-filter:none; }
    .bar{ background: var(--surface-solid); }
    .card{ background: var(--surface-solid); }
    .chips-row{ background: var(--bg); }
  }
  @media (prefers-contrast: more){
    :root{ --line: rgba(0,0,0,.30); --line-strong: rgba(0,0,0,.52); --ink-3:#3d3d46; --ink-2:#1c1c22; }
    .card{ border-width: 2px; }
    .card p{ color: var(--ink); }
  }
  html[data-theme="dark"] #pill{ background: var(--pill); }
</style>
</head>
<body>

<div class="bar">
  <div class="bar-in">
    <a class="brand" href="#top" aria-label="Início">
      <span class="dot" aria-hidden="true"></span>
      <span class="full">Dashboards</span>
    </a>
    <div class="grow"></div>
    <div class="search" role="search">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <circle cx="7" cy="7" r="4.6"></circle><path d="M10.6 10.6L14 14" stroke-linecap="round"></path>
      </svg>
      <input id="q" type="search" placeholder="Buscar painel, lei, assunto…"
             autocomplete="off" spellcheck="false" aria-label="Buscar painel">
      <kbd>/</kbd>
    </div>
    <button class="iconbtn" id="theme" type="button" aria-label="Alternar tema claro e escuro" title="Tema claro / escuro">
      <svg id="ico-theme" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
        <circle cx="8" cy="8" r="3.2"></circle>
        <path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3 3l1.1 1.1M11.9 11.9L13 13M13 3l-1.1 1.1M4.1 11.9L3 13" stroke-linecap="round"></path>
      </svg>
    </button>
  </div>
</div>

<header class="hero" id="top">
  <div class="eyebrow"><span class="pip"></span>Conta Vercel · sherpachsl</div>
  <h1>__TOTAL__ dashboards, por assunto.</h1>
  <p class="dek">Todo painel estático publicado na conta Vercel, agrupado por tema — trabalho no MPPE, leis artigo a artigo, guias de livros, mercado, eleições, saúde e o resto. Os painéis marcados com cadeado pedem senha na entrada.</p>
  <div class="stats">
    <div class="stat"><b>__TOTAL__</b><span>painéis</span></div>
    <div class="stat"><b>__NCAT__</b><span>assuntos</span></div>
    <div class="stat"><b>__GATED__</b><span>com senha</span></div>
    <div class="stat"><b>__ABERTOS__</b><span>abertos</span></div>
  </div>
</header>

<div class="chips-row">
  <div class="chips-wrap">
    <div class="chips" role="tablist" aria-label="Filtrar por assunto">
      <div id="pill" aria-hidden="true"></div>
      __CHIPS__
    </div>
  </div>
</div>

<main>
  __GRUPOS__
  <div class="empty" id="empty">
    <b>Nada com esse termo.</b>
    Tente outro nome, lei ou assunto — a busca ignora acentos.
  </div>
</main>

<footer>
  <p><b>Índice gerado a partir da API do Vercel</b> — <span id="stamp">__STAMP__</span> · __TOTAL__ projetos, um card cada.</p>
  <p>As senhas dos painéis fechados não ficam nesta página: estão na nota <i>Projetos Vercel</i> do vault (<code>015_HERMES/vercel/</code>). Os links abrem no alias estável <code>&lt;projeto&gt;.vercel.app</code>.</p>
  <p><a href="https://vercel.com/dashboard" target="_blank" rel="noopener">vercel.com/dashboard</a></p>
</footer>

<script id="dados" type="application/json">__DATA__</script>
<script>
(function(){
  "use strict";
  var DATA = JSON.parse(document.getElementById('dados').textContent);
  var CATS = DATA.cats, ITENS = DATA.itens;

  var q = document.getElementById('q');
  var pill = document.getElementById('pill');
  var chipsBox = document.querySelector('.chips');
  var main = document.querySelector('main');
  var empty = document.getElementById('empty');
  var state = { cat: 'all', termo: '' };

  /* ---------- normalização (sem acento, sem caixa) ---------- */
  function norm(s){
    return (s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  }
  var porNome = {};
  Array.prototype.forEach.call(document.querySelectorAll('.card'), function(el){
    porNome[el.dataset.n] = el;
  });
  ITENS.forEach(function(it){
    it.el = porNome[it.n];
    it._h = norm(it.t + ' ' + it.d + ' ' + it.catT + ' ' + it.host);
  });

  /* ---------- mola: interrompível, parte do valor atual ---------- */
  var rafPill = 0;
  function moverPill(alvoX, alvoW, v0){
    if (rafPill) cancelAnimationFrame(rafPill);
    var x = parseFloat(pill.dataset.x || '0'),
        w = parseFloat(pill.dataset.w || '0'),
        vx = v0 || 0, vw = 0, inicio = null, acc = 0;
    // mola criticamente amortecida (damping 1.0, resposta ~0.34 s)
    var omega = 2 * Math.PI / 0.34, zeta = 1.0;
    var k = omega * omega, c = 2 * zeta * omega, PASSO = 1 / 240;
    function step(ts){
      if (inicio === null) inicio = ts;
      var dt = (ts - ultimo) / 1000; ultimo = ts;
      acc += Math.min(dt, 0.25);                 // absorve frames longos
      var guarda = 0;
      while (acc > 0 && guarda++ < 400){         // integração em passos fixos
        var h = Math.min(PASSO, acc); acc -= h;
        vx += (-k * (x - alvoX) - c * vx) * h;
        x  += vx * h;
        vw += (-k * (w - alvoW) - c * vw) * h;
        w  += vw * h;
      }
      var terminou = (ts - inicio) > 1400;
      if (terminou || (Math.abs(x - alvoX) < 0.12 && Math.abs(vx) < 3 &&
          Math.abs(w - alvoW) < 0.12 && Math.abs(vw) < 3)){
        x = alvoX; w = alvoW;
        pill.style.transform = 'translateX(' + x + 'px)';
        pill.style.width = w + 'px';
        pill.dataset.x = x; pill.dataset.w = w;
        rafPill = 0;
        return;
      }
      pill.style.transform = 'translateX(' + x + 'px)';
      pill.style.width = w + 'px';
      pill.dataset.x = x; pill.dataset.w = w;
      rafPill = requestAnimationFrame(step);
    }
    var ultimo = performance.now();
    rafPill = requestAnimationFrame(step);
  }

  var reduzido = window.matchMedia('(prefers-reduced-motion: reduce)');
  function posicionarPill(chip, animar){
    if (!chip) return;
    var alvoX = chip.offsetLeft, alvoW = chip.offsetWidth;
    if (animar && !reduzido.matches){ moverPill(alvoX, alvoW); }
    else {
      pill.style.transform = 'translateX(' + alvoX + 'px)';
      pill.style.width = alvoW + 'px';
      pill.dataset.x = alvoX; pill.dataset.w = alvoW;
    }
  }

  function chipAtivo(){ return chipsBox.querySelector('.chip[aria-selected="true"]'); }

  /* ---------- render ---------- */
  var gruposEls = {};
  Array.prototype.forEach.call(document.querySelectorAll('section.group'), function(sec){
    gruposEls[sec.dataset.cat] = sec;
  });

  function aplicar(inicio){
    var termo = norm(state.termo).trim();
    var visiveis = 0, porCat = {};
    ITENS.forEach(function(it){
      var okCat = state.cat === 'all' || it.cat === state.cat;
      var okTermo = !termo || it._h.indexOf(termo) !== -1;
      var el = it.el;
      var mostrar = okCat && okTermo;
      el.hidden = !mostrar;
      if (mostrar){
        visiveis++;
        porCat[it.cat] = (porCat[it.cat] || 0) + 1;
        if (inicio){
          el.classList.remove('enter');
          void el.offsetWidth;
          el.classList.add('enter');
          el.style.animationDelay = Math.min(visiveis * 14, 260) + 'ms';
        }
      }
    });
    Object.keys(gruposEls).forEach(function(cat){
      var sec = gruposEls[cat];
      var n = porCat[cat] || 0;
      sec.hidden = n === 0;
      sec.querySelector('.count').textContent = n === 1 ? '1 painel' : n + ' painéis';
    });
    empty.classList.toggle('show', visiveis === 0);
  }

  /* ---------- chips ---------- */
  function selecionar(cat, animar){
    state.cat = cat;
    Array.prototype.forEach.call(chipsBox.querySelectorAll('.chip'), function(c){
      c.setAttribute('aria-selected', String(c.dataset.cat === cat));
      c.tabIndex = c.dataset.cat === cat ? 0 : -1;
    });
    posicionarPill(chipAtivo(), animar !== false);
    var ativo = chipAtivo();
    if (ativo){                                  /* traz o chip escolhido à vista */
      var r = ativo.getBoundingClientRect(), box = chipsBox.getBoundingClientRect();
      if (r.left < box.left + 5) chipsBox.scrollLeft -= (box.left + 5 - r.left);
      else if (r.right > box.right - 5) chipsBox.scrollLeft += (r.right - box.right + 5);
    }
    aplicar(true);
  }

  chipsBox.addEventListener('click', function(e){
    var chip = e.target.closest('.chip');
    if (!chip) return;
    selecionar(chip.dataset.cat);
  });
  chipsBox.addEventListener('keydown', function(e){
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    var chips = Array.prototype.slice.call(chipsBox.querySelectorAll('.chip'));
    var i = chips.indexOf(document.activeElement), d = e.key === 'ArrowRight' ? 1 : -1;
    var alvo = chips[(i + d + chips.length) % chips.length];
    if (alvo){
      e.preventDefault();
      alvo.focus({ preventScroll: true });
      selecionar(alvo.dataset.cat);
      var r = alvo.getBoundingClientRect(), box = chipsBox.getBoundingClientRect();
      if (r.left < box.left || r.right > box.right){
        chipsBox.scrollLeft += r.left - box.left - 8;
      }
    }
  });

  /* ---------- busca ---------- */
  var t = null;
  q.addEventListener('input', function(){
    state.termo = q.value;
    if (t) clearTimeout(t);
    t = setTimeout(function(){ aplicar(false); }, 60);
  });
  q.addEventListener('keydown', function(e){
    if (e.key === 'Escape'){ q.value = ''; state.termo = ''; aplicar(false); q.blur(); }
  });
  document.addEventListener('keydown', function(e){
    if (e.key === '/' && document.activeElement !== q){
      e.preventDefault(); q.focus(); q.select();
    }
  });

  /* ---------- tema ---------- */
  var raiz = document.documentElement;
  var btn = document.getElementById('theme');
  function temaSistema(){
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function pintarIcone(){
    var escuro = (raiz.dataset.theme === 'dark') ||
                 (raiz.dataset.theme === 'auto' && temaSistema() === 'dark');
    document.getElementById('ico-theme').style.transform = escuro ? 'rotate(180deg)' : 'none';
  }
  btn.addEventListener('click', function(){
    var atual = (raiz.dataset.theme === 'auto') ? temaSistema() : raiz.dataset.theme;
    raiz.dataset.theme = atual === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('idx-tema', raiz.dataset.theme); } catch(_){}
    pintarIcone();
  });
  try {
    var salvo = localStorage.getItem('idx-tema');
    if (salvo === 'light' || salvo === 'dark') raiz.dataset.theme = salvo;
  } catch(_){}
  pintarIcone();

  /* ---------- início ---------- */
  selecionar('all', false);
  requestAnimationFrame(function(){ posicionarPill(chipAtivo(), false); });
  window.addEventListener('resize', function(){ posicionarPill(chipAtivo(), false); });
  if (document.fonts && document.fonts.ready){
    document.fonts.ready.then(function(){ posicionarPill(chipAtivo(), false); });
  }
})();
</script>
</body>
</html>
"""


def build():
    inv = inventario()
    faltando = sorted(set(inv) - {n for n, _, _ in ITENS})
    if faltando:
        raise SystemExit("projetos sem classificação: " + ", ".join(faltando))
    extras = sorted({n for n, _, _ in ITENS} - set(inv))
    if extras:
        raise SystemExit("classificados que não existem na conta: " + ", ".join(extras))

    itens = []
    for nome, cat, desc in ITENS:
        info = inv[nome]
        host = info["host"]
        if not host.endswith(".vercel.app"):
            host += ".vercel.app"
        itens.append({
            "n": nome,
            "cat": cat,
            "catT": CAT[cat][0],
            "t": info.get("title") or TITULO_RESERVA.get(nome) or nome.replace("-", " "),
            "d": desc,
            "host": host,
            "url": "https://" + host,
            "lock": bool(info.get("gate")),
        })

    ordem = ["mppe", "lei", "juris", "livro", "economia",
             "politica", "saude", "imprensa", "tech", "pessoal"]
    itens.sort(key=lambda x: (ordem.index(x["cat"]), x["t"].lower()))

    contagem = {}
    for it in itens:
        contagem[it["cat"]] = contagem.get(it["cat"], 0) + 1

    chips = ['<button class="chip" role="tab" data-cat="all" aria-selected="true">'
             f'Todos<span class="n">{len(itens)}</span></button>']
    for cat in ordem:
        chips.append('<button class="chip" role="tab" data-cat="%s" aria-selected="false">'
                     '%s<span class="n">%d</span></button>'
                     % (cat, CAT[cat][1], contagem.get(cat, 0)))

    grupos = []
    for cat in ordem:
        doGrupo = [i for i in itens if i["cat"] == cat]
        if not doGrupo:
            continue
        cards = []
        for i in doGrupo:
            cadeado = ('<span class="lock" title="Protegido por senha">'
                       '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" '
                       'stroke-width="1.5"><rect x="2.2" y="5.2" width="7.6" height="5.4" '
                       'rx="1.3"></rect><path d="M4 5.2V3.9a2 2 0 014 0v1.3" stroke-linecap="round">'
                       '</path></svg>Senha</span>') if i["lock"] else ''
            cards.append(
                '<a class="card" href="{url}" target="_blank" rel="noopener" data-n="{n}">'
                '{lock}<h3>{t}</h3><p>{d}</p>'
                '<div class="meta"><span class="host">{host}</span>'
                '<span class="arrow" aria-hidden="true"><svg viewBox="0 0 14 14" fill="none" '
                'stroke="currentColor" stroke-width="1.6"><path d="M4 10L10 4M10 4H5.2M10 4v4.8" '
                'stroke-linecap="round" stroke-linejoin="round"></path></svg></span></div></a>'
                .format(**{k: str(i[k]).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
                           for k in ("url", "t", "d", "host", "n")},
                        lock=cadeado))

        grupos.append(
            '<section class="group" data-cat="%s" id="cat-%s">'
            '<div class="group-head"><h2>%s</h2><span class="rule"></span>'
            '<span class="count">%d painéis</span></div>'
            '<div class="grid">%s</div></section>'
            % (cat, cat, CAT[cat][0], len(doGrupo), "".join(cards)))

    dados = json.dumps({
        "cats": {k: v[0] for k, v in CAT.items()},
        "itens": [{k: v for k, v in i.items() if k in ("n", "cat", "catT", "t", "d", "host")}
                  for i in itens],
    }, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    from datetime import datetime, timezone, timedelta
    stamp = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")

    html = (TEMPLATE
            .replace("__CHIPS__", "".join(chips))
            .replace("__GRUPOS__", "".join(grupos))
            .replace("__DATA__", dados)
            .replace("__STAMP__", stamp)
            .replace("__TOTAL__", str(len(itens)))
            .replace("__NCAT__", str(len([c for c in ordem if contagem.get(c)])))
            .replace("__GATED__", str(sum(1 for i in itens if i["lock"])))
            .replace("__ABERTOS__", str(sum(1 for i in itens if not i["lock"]))))

    out = os.path.join(HERE, "index.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"{out} · {len(itens)} painéis · {len(html)/1024:.0f} KB")


if __name__ == "__main__":
    build()
