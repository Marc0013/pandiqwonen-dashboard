"""
PandIQ Wonen Dashboard — generator.
Leest data uit gekoppelde bronnen en genereert index.html.

Gebruik:
    python generate_dashboard.py
"""

import html as html_module
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
OUTPUT       = BASE_DIR / "index.html"

ISDE_DIR     = Path(__file__).parent.parent / "07 Scaper ISDE subsidies"
ISDE_REPORTS = ISDE_DIR / "data" / "reports"


# ---------------------------------------------------------------------------
# Data inlezen — ISDE
# ---------------------------------------------------------------------------

def _parse_rapport(tekst: str, pad: Path) -> dict:
    result = {"bestand": pad.name, "datum": "", "secties": []}
    datum_match = re.search(r"Datum:\s*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})", tekst)
    if datum_match:
        result["datum"] = datum_match.group(1)
    secties_raw = re.split(r"\n\s{2}([A-Z][A-Z +]+)\n", tekst)
    huidige_naam = None
    for deel in secties_raw:
        deel = deel.strip()
        if re.match(r"^[A-Z][A-Z +]+$", deel):
            huidige_naam = deel
        elif huidige_naam:
            sectie = _parse_sectie(huidige_naam, deel)
            if sectie:
                result["secties"].append(sectie)
            huidige_naam = None
    return result


def _parse_sectie(naam: str, tekst: str) -> dict:
    records_match = re.search(r"Records:\s*(\d+)\s*\(vorig\)\s*→\s*(\d+)\s*\(nieuw\)", tekst)
    totaal_match  = re.search(r"Totaal:\s*(\d+) nieuw,\s*(\d+) vervallen,\s*(\d+) gewijzigd", tekst)
    if not totaal_match and not records_match:
        return {}
    vorig, nieuw_rec = (int(records_match.group(1)), int(records_match.group(2))) if records_match else (0, 0)
    n_nieuw     = int(totaal_match.group(1)) if totaal_match else 0
    n_vervallen = int(totaal_match.group(2)) if totaal_match else 0
    n_gewijzigd = int(totaal_match.group(3)) if totaal_match else 0
    return {
        "naam": naam.title(),
        "records_vorig": vorig, "records_nieuw": nieuw_rec,
        "n_nieuw": n_nieuw, "n_vervallen": n_vervallen, "n_gewijzigd": n_gewijzigd,
        "nieuw":     re.findall(r"\+\s+(KA\d+)\s+(.+?)\s{2,}(.+)", tekst),
        "vervallen": re.findall(r"-\s+(KA\d+)\s+(.+?)\s{2,}(.+)", tekst),
        "gewijzigd": _parse_gewijzigd(tekst),
    }


def _parse_gewijzigd(tekst: str) -> list:
    items = []
    for ka, merk, model, details_raw in re.findall(
        r"~\s+(KA\d+)\s+(.+?)\s{2,}(.+?)\n((?:\s{9}.+\n?)*)", tekst
    ):
        details = re.findall(r"(\w+):\s+([\d.None]+)\s*→\s*([\d.None]+)", details_raw)
        items.append({
            "ka": ka, "merk": merk.strip(), "model": model.strip(),
            "details": [{"veld": v, "oud": o, "nieuw": n} for v, o, n in details],
        })
    return items


def verzamel_isde_data() -> list:
    rapporten = sorted(ISDE_REPORTS.glob("isde_rapport_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    gezien, secties = set(), []
    for rapport in rapporten[:10]:
        parsed = _parse_rapport(rapport.read_text(encoding="utf-8"), rapport)
        for sectie in parsed.get("secties", []):
            if sectie["naam"] not in gezien:
                gezien.add(sectie["naam"])
                sectie["rapport_datum"] = parsed.get("datum", "")
                secties.append(sectie)
    return secties


# ---------------------------------------------------------------------------
# Data inlezen — Audit & Trends
# ---------------------------------------------------------------------------

def lees_audit_data() -> dict:
    pad = DATA_DIR / "site_audit.json"
    if not pad.exists():
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except Exception:
        return {}


def lees_trends_data() -> dict:
    pad = DATA_DIR / "trends.json"
    if not pad.exists():
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# HTML — ISDE
# ---------------------------------------------------------------------------

def _badge(getal: int, kleur: str, label: str) -> str:
    if getal == 0:
        return f'<span class="badge badge-leeg">0 {label}</span>'
    prefix = f"{getal:+d}" if label in ("nieuw", "vervallen") else str(getal)
    return f'<span class="badge badge-{kleur}">{prefix} {label}</span>'


def _sectie_html(s: dict) -> str:
    heeft_wijzigingen = s["n_nieuw"] or s["n_vervallen"] or s["n_gewijzigd"]
    records_tekst = (
        f'<span class="records">{s["records_vorig"]} → {s["records_nieuw"]} records</span>'
        if s["records_vorig"] != s["records_nieuw"]
        else f'<span class="records">{s["records_nieuw"]} records</span>'
    )

    details_html = ""
    if heeft_wijzigingen:
        rijen = []
        for ka, merk, model in s["nieuw"]:
            rijen.append(f'<tr class="rij-nieuw"><td class="ka">{ka}</td><td>{merk}</td><td>{model}</td><td><em>Nieuw toegevoegd</em></td></tr>')
        for ka, merk, model in s["vervallen"]:
            rijen.append(f'<tr class="rij-vervallen"><td class="ka">{ka}</td><td>{merk}</td><td>{model}</td><td><em>Vervallen</em></td></tr>')
        for item in s["gewijzigd"]:
            detail_tekst = ", ".join(f'{d["veld"]}: {d["oud"]} → {d["nieuw"]}' for d in item["details"]) or "gewijzigd"
            rijen.append(
                f'<tr class="rij-gewijzigd"><td class="ka">{item["ka"]}</td>'
                f'<td>{item["merk"]}</td><td>{item["model"]}</td>'
                f'<td class="detail-tekst">{detail_tekst}</td></tr>'
            )
        if rijen:
            details_html = f"""
            <div class="details">
                <table>
                    <thead><tr><th>Code</th><th>Merk</th><th>Model</th><th>Wijziging</th></tr></thead>
                    <tbody>{"".join(rijen)}</tbody>
                </table>
            </div>"""

    toggle = 'onclick="toggle(this)"' if heeft_wijzigingen else ""
    cursor = "cursor:pointer" if heeft_wijzigingen else ""
    pijl   = '<span class="pijl">▸</span> ' if heeft_wijzigingen else ""

    return f"""
    <div class="sectie">
        <div class="sectie-header" {toggle} style="{cursor}">
            <div class="sectie-titel">{pijl}{s["naam"]}</div>
            <div class="sectie-badges">
                {records_tekst}
                {_badge(s["n_nieuw"], "groen", "nieuw")}
                {_badge(s["n_vervallen"], "rood", "vervallen")}
                {_badge(s["n_gewijzigd"], "oranje", "gewijzigd")}
            </div>
        </div>
        {details_html}
    </div>"""


# ---------------------------------------------------------------------------
# HTML — Site Audit
# ---------------------------------------------------------------------------

def _audit_groepen(data: dict) -> list:
    fouten, geen_meta, geen_alt, traag, geen_h1 = [], [], [], [], []
    for r in data.get("resultaten", []):
        url = html_module.escape(r["url"])
        for f in r.get("fouten", []):
            fouten.append((url, html_module.escape(f)))
        for w in r.get("waarschuwingen", []):
            w_lower = w.lower()
            if "meta-beschrijving" in w_lower:
                geen_meta.append((url, html_module.escape(w)))
            elif "alt-tekst" in w_lower:
                geen_alt.append((url, html_module.escape(w)))
            elif "traag" in w_lower:
                traag.append((url, html_module.escape(w)))
            elif "h1" in w_lower:
                geen_h1.append((url, html_module.escape(w)))

    externe_fouten = [
        (html_module.escape(e["url"]), f"HTTP {e['status']}")
        for e in data.get("externe_fouten", [])
    ]

    groepen = []
    if fouten:
        groepen.append(("Kapotte pagina's", "rood", fouten))
    if externe_fouten:
        groepen.append(("Kapotte externe links", "rood", externe_fouten))
    if traag:
        groepen.append(("Trage pagina's (&gt;3s)", "oranje", traag))
    if geen_meta:
        groepen.append(("Ontbrekende meta-beschrijving", "oranje", geen_meta))
    if geen_alt:
        groepen.append(("Afbeeldingen zonder alt-tekst", "oranje", geen_alt))
    if geen_h1:
        groepen.append(("Pagina's zonder H1", "oranje", geen_h1))
    return groepen


def _audit_html(data: dict) -> str:
    if not data:
        return """
  <div class="blok">
    <div class="blok-titel">Site Audit — wonen.pandiq.nl</div>
    <div class="leeg-melding">Nog niet uitgevoerd &nbsp;·&nbsp; Draai <code>python site_audit.py</code> om te starten</div>
  </div>"""

    n_paginas = data.get("paginas_gecontroleerd", 0)
    n_fouten  = data.get("n_fouten", 0) + len(data.get("externe_fouten", []))
    n_warns   = data.get("n_waarschuwingen", 0)
    datum     = html_module.escape(data.get("datum", ""))

    stat_fout = (
        f'<span class="audit-stat audit-fout">&#10007; {n_fouten} fout{"en" if n_fouten != 1 else ""}</span>'
        if n_fouten else
        '<span class="audit-stat audit-ok">&#10003; geen fouten</span>'
    )
    stat_warn = (
        f'<span class="audit-stat audit-warn">&#9888; {n_warns} waarschuwing{"en" if n_warns != 1 else ""}</span>'
        if n_warns else
        '<span class="audit-stat audit-ok">&#10003; geen waarschuwingen</span>'
    )

    groepen = _audit_groepen(data)
    groepen_html = ""
    for naam, kleur, items in groepen:
        rijen = "".join(
            f'<tr><td class="audit-url">{url}</td><td class="audit-melding">{melding}</td></tr>'
            for url, melding in items[:50]
        )
        if len(items) > 50:
            rijen += f'<tr><td colspan="2" class="audit-melding">... en {len(items) - 50} meer</td></tr>'
        groepen_html += f"""
    <div class="sectie">
      <div class="sectie-header" onclick="toggle(this)" style="cursor:pointer">
        <div class="sectie-titel"><span class="pijl">&#9658;</span> {naam}</div>
        <div class="sectie-badges"><span class="badge badge-{kleur}">{len(items)}</span></div>
      </div>
      <div class="details"><table><tbody>{rijen}</tbody></table></div>
    </div>"""

    if not groepen_html:
        groepen_html = '<div class="audit-perfect">&#10003; Alles ziet er goed uit — geen problemen gevonden.</div>'

    return f"""
  <div class="blok">
    <div class="blok-titel">Site Audit — wonen.pandiq.nl</div>
    <div class="audit-status">
      <span class="audit-stat audit-ok">&#10003; {n_paginas} pagina's gecontroleerd</span>
      {stat_fout}
      {stat_warn}
      <span class="audit-meta">Gecontroleerd op {datum}</span>
    </div>
    {groepen_html}
  </div>"""


# ---------------------------------------------------------------------------
# HTML — Zoektrends
# ---------------------------------------------------------------------------

def _trends_html(data: dict) -> str:
    if not data:
        return """
  <div class="blok">
    <div class="blok-titel">Zoektrends — Google NL</div>
    <div class="leeg-melding">Nog niet uitgevoerd &nbsp;·&nbsp; Draai <code>python trends.py</code> om te starten</div>
  </div>"""

    termen  = data.get("termen", [])
    datum   = html_module.escape(data.get("datum", ""))
    periode = html_module.escape(data.get("periode", ""))

    kaarten = ""
    for t in termen:
        richting   = t.get("richting", "stabiel")
        verandering = t.get("verandering", 0)
        term       = html_module.escape(t.get("term", ""))
        waarden    = t.get("waarden", [])
        fout       = t.get("fout", "")

        if richting == "op":
            pijl, kleur, bar_class = "&#8593;", "trend-op", "trend-bar-op"
            verandering_tekst = f"+{verandering}%"
        elif richting == "neer":
            pijl, kleur, bar_class = "&#8595;", "trend-neer", "trend-bar-neer"
            verandering_tekst = f"{verandering}%"
        else:
            pijl, kleur, bar_class = "&#8594;", "trend-stabiel", "trend-bar-stabiel"
            verandering_tekst = "stabiel"

        bars = "".join(
            f'<div class="trend-bar {bar_class}" style="height:{max(3, v)}%"></div>'
            for v in waarden[-13:]
        )
        huidig = t.get("huidig", 0)

        if fout or not bars:
            kaarten += f"""
      <div class="trend-kaart trend-kaart-fout">
        <div class="trend-naam">{term}</div>
        <div class="trend-richting trend-stabiel">&#8212; geen data</div>
        <div class="trend-bars-leeg"></div>
        <div class="trend-meta">Kon niet ophalen</div>
      </div>"""
        else:
            kaarten += f"""
      <div class="trend-kaart">
        <div class="trend-naam">{term}</div>
        <div class="trend-richting {kleur}">{pijl} {verandering_tekst}</div>
        <div class="trend-bars">{bars}</div>
        <div class="trend-meta">Score nu: {huidig}/100</div>
      </div>"""

    return f"""
  <div class="blok">
    <div class="blok-titel">Zoektrends — Google NL</div>
    <div class="trends-grid">{kaarten}
    </div>
    <div class="trends-footer">Bron: Google Trends &nbsp;&#183;&nbsp; {periode} &nbsp;&#183;&nbsp; Bijgewerkt op {datum} &nbsp;&#183;&nbsp; Zoektermen aanpassen: <code>zoektermen.txt</code></div>
  </div>"""


# ---------------------------------------------------------------------------
# HTML — Alles samenvoegen
# ---------------------------------------------------------------------------

def genereer_html(isde_secties: list, audit_data: dict, trends_data: dict) -> str:
    nu = datetime.now().strftime("%d-%m-%Y %H:%M")

    secties_html = "".join(_sectie_html(s) for s in isde_secties)
    audit_blok   = _audit_html(audit_data)
    trends_blok  = _trends_html(trends_data)

    heeft_wijzigingen = any(s["n_nieuw"] or s["n_vervallen"] or s["n_gewijzigd"] for s in isde_secties)
    samenvatting = "Geen wijzigingen gevonden." if not heeft_wijzigingen else (
        f'{sum(s["n_nieuw"] for s in isde_secties)} nieuw &nbsp;&middot;&nbsp; '
        f'{sum(s["n_vervallen"] for s in isde_secties)} vervallen &nbsp;&middot;&nbsp; '
        f'{sum(s["n_gewijzigd"] for s in isde_secties)} gewijzigd'
    )

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PandIQ Wonen Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f4f6f9; color: #1a1a2e; font-size: 15px; }}

  /* Header */
  header {{ background: #1a1a2e; color: white; padding: 20px 32px; display: flex;
            align-items: center; justify-content: space-between; }}
  header h1 {{ font-size: 20px; font-weight: 600; letter-spacing: .5px; }}
  header .update {{ font-size: 13px; opacity: .65; }}

  /* Basisblokken */
  .samenvatting {{ background: white; border-left: 4px solid #4a90d9;
                   margin: 24px 32px 8px; padding: 14px 20px; border-radius: 6px;
                   font-size: 14px; color: #444; box-shadow: 0 1px 4px rgba(0,0,0,.07); }}
  .blok {{ background: white; margin: 8px 32px; border-radius: 8px;
           box-shadow: 0 1px 4px rgba(0,0,0,.07); overflow: hidden; }}
  .blok-titel {{ font-size: 12px; font-weight: 700; letter-spacing: 1px;
                 text-transform: uppercase; color: #888; padding: 16px 20px 8px; }}

  /* Secties (inklapbaar) */
  .sectie {{ border-top: 1px solid #f0f0f0; }}
  .sectie-header {{ display: flex; align-items: center; justify-content: space-between;
                    padding: 13px 20px; gap: 12px; user-select: none; }}
  .sectie-header:hover {{ background: #fafafa; }}
  .sectie-titel {{ font-weight: 500; font-size: 15px; display: flex; align-items: center; gap: 6px; }}
  .pijl {{ color: #aaa; font-size: 12px; transition: transform .2s; display: inline-block; }}
  .pijl.open {{ transform: rotate(90deg); }}
  .sectie-badges {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .records {{ font-size: 12px; color: #999; }}

  /* Badges */
  .badge {{ font-size: 12px; padding: 3px 9px; border-radius: 12px; font-weight: 600; }}
  .badge-leeg   {{ background: #f0f0f0; color: #bbb; }}
  .badge-groen  {{ background: #e6f4ea; color: #2e7d32; }}
  .badge-rood   {{ background: #fdecea; color: #c62828; }}
  .badge-oranje {{ background: #fff3e0; color: #e65100; }}

  /* Tabellen */
  .details {{ border-top: 1px solid #f5f5f5; padding: 0 20px 16px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }}
  th {{ text-align: left; padding: 7px 10px; background: #f8f8f8;
        color: #666; font-weight: 600; font-size: 12px; border-bottom: 1px solid #eee; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #f5f5f5; vertical-align: top; }}
  .ka {{ font-family: monospace; color: #888; font-size: 12px; white-space: nowrap; }}
  .rij-nieuw     td {{ background: #f6fef7; }}
  .rij-vervallen td {{ background: #fff8f8; }}
  .rij-gewijzigd td {{ background: #fffdf5; }}
  .detail-tekst {{ color: #555; font-size: 12px; }}

  /* Leeg-melding */
  .leeg-melding {{ padding: 20px; color: #bbb; font-size: 14px; border-top: 1px solid #f0f0f0; }}
  .leeg-melding code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px;
                         font-family: monospace; font-size: 12px; color: #666; }}

  /* Site Audit */
  .audit-status {{ display: flex; align-items: center; gap: 20px; padding: 14px 20px;
                   border-top: 1px solid #f0f0f0; flex-wrap: wrap; }}
  .audit-stat {{ font-size: 13px; font-weight: 600; }}
  .audit-ok   {{ color: #2e7d32; }}
  .audit-fout {{ color: #c62828; }}
  .audit-warn {{ color: #e65100; }}
  .audit-meta {{ font-size: 12px; color: #bbb; margin-left: auto; }}
  .audit-url {{ word-break: break-all; color: #444; max-width: 420px; }}
  .audit-melding {{ color: #999; font-size: 12px; padding-left: 8px; white-space: nowrap; }}
  .audit-perfect {{ padding: 18px 20px; color: #2e7d32; font-weight: 500; font-size: 14px;
                    border-top: 1px solid #f0f0f0; }}

  /* Zoektrends */
  .trends-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
                  gap: 1px; background: #efefef; border-top: 1px solid #f0f0f0; }}
  .trend-kaart {{ background: white; padding: 18px 20px 14px; transition: background .15s; }}
  .trend-kaart:hover {{ background: #fafbff; }}
  .trend-kaart-fout {{ opacity: .5; }}
  .trend-naam {{ font-weight: 700; font-size: 13px; color: #1a1a2e; margin-bottom: 6px;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .trend-richting {{ font-size: 24px; font-weight: 800; margin-bottom: 10px; line-height: 1; }}
  .trend-op     {{ color: #2e7d32; }}
  .trend-neer   {{ color: #c62828; }}
  .trend-stabiel {{ color: #888; }}
  .trend-bars {{ display: flex; align-items: flex-end; height: 44px; gap: 2px; margin-bottom: 8px; }}
  .trend-bar {{ flex: 1; min-height: 3px; border-radius: 2px 2px 0 0; transition: opacity .2s; }}
  .trend-kaart:hover .trend-bar {{ opacity: .85; }}
  .trend-bar:last-child {{ opacity: 1 !important; }}
  .trend-bar-op     {{ background: linear-gradient(to top, #2e7d32, #66bb6a); }}
  .trend-bar-neer   {{ background: linear-gradient(to top, #c62828, #ef9a9a); }}
  .trend-bar-stabiel {{ background: linear-gradient(to top, #1a6bc4, #4a90d9); }}
  .trend-bars-leeg {{ height: 44px; margin-bottom: 8px; }}
  .trend-meta {{ font-size: 11px; color: #bbb; }}
  .trends-footer {{ padding: 11px 20px; font-size: 12px; color: #bbb;
                    border-top: 1px solid #f0f0f0; }}
  .trends-footer code {{ background: #f4f4f4; padding: 1px 5px; border-radius: 3px;
                          font-family: monospace; font-size: 11px; color: #888; }}

  /* Footer */
  .footer {{ text-align: center; padding: 32px; font-size: 12px; color: #bbb; }}
</style>
</head>
<body>

<header>
  <h1>PandIQ Wonen — Dashboard</h1>
  <span class="update">Laatste update: {nu}</span>
</header>

<div class="samenvatting">
  <strong>ISDE subsidies</strong> &nbsp;&middot;&nbsp; {samenvatting}
</div>

<div class="blok">
  <div class="blok-titel">ISDE Subsidies</div>
  {secties_html}
</div>

{trends_blok}

{audit_blok}

<div class="footer">Gegenereerd op {nu} &nbsp;&middot;&nbsp; PandIQ</div>

<script>
function toggle(el) {{
  const details = el.nextElementSibling;
  const pijl = el.querySelector('.pijl');
  if (!details) return;
  const open = details.style.display === 'none' || details.style.display === '';
  details.style.display = open ? 'block' : 'none';
  if (pijl) pijl.classList.toggle('open', open);
}}
document.querySelectorAll('.details').forEach(d => d.style.display = 'none');
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------

def main():
    print("Dashboard genereren...")
    isde_secties = verzamel_isde_data()
    audit_data   = lees_audit_data()
    trends_data  = lees_trends_data()

    html = genereer_html(isde_secties, audit_data, trends_data)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"  index.html geschreven ({len(html):,} tekens)")

    dashboard_dir = str(BASE_DIR)
    subprocess.run(["git", "add", "index.html"], cwd=dashboard_dir, check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=dashboard_dir,
    )
    if result.returncode != 0:
        nu = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"Dashboard update {nu}"],
            cwd=dashboard_dir, check=True,
        )
        push = subprocess.run(["git", "push", "origin", "main"], cwd=dashboard_dir)
        if push.returncode == 0:
            print("  Gepusht naar GitHub Pages.")
        else:
            print("  Push mislukt — remote nog niet gekoppeld?")
    else:
        print("  Geen wijzigingen — niets gepusht.")


if __name__ == "__main__":
    main()
