"""
PandIQ Site Audit — controleert wonen.pandiq.nl op:
  - Kapotte links (4xx / 5xx)
  - Trage pagina's (> 3 seconden)
  - Afbeeldingen zonder alt-tekst
  - Ontbrekende meta-beschrijving
  - Pagina's zonder H1

Eenmalig installeren (in terminal):
    pip install requests beautifulsoup4

Gebruik:
    python site_audit.py

Resultaat wordt opgeslagen in data/site_audit.json
en is zichtbaar na het draaien van generate_dashboard.py
"""

import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
OUTPUT        = DATA_DIR / "site_audit.json"
DATA_DIR.mkdir(exist_ok=True)

STARTURL      = "https://wonen.pandiq.nl"
SITEMAP_URL   = "https://wonen.pandiq.nl/sitemap.xml"
DOMEIN        = "wonen.pandiq.nl"
TIMEOUT       = 10       # seconden per request
TRAAG_DREMPEL = 3.0      # seconden voor "traag"
MAX_PAGINAS   = 300      # veiligheidsgrens
MAX_EXTERN    = 50       # max externe links checken

HEADERS = {"User-Agent": "PandIQ-Audit-Bot/1.0 (intern dashboard)"}


def _zelfde_domein(url: str) -> bool:
    return urlparse(url).netloc in ("", DOMEIN)


def _normaliseer(url: str, basis: str) -> str:
    volledig = urljoin(basis, url).split("#")[0].rstrip("/")
    parsed = urlparse(volledig)
    return parsed._replace(fragment="").geturl().rstrip("/")


def _haal_urls_uit_sitemap(sessie: requests.Session, sitemap_url: str, gezien: set = None) -> list:
    """Leest een sitemap (of sitemap-index) en geeft alle pagina-URLs terug."""
    if gezien is None:
        gezien = set()
    if sitemap_url in gezien:
        return []
    gezien.add(sitemap_url)

    urls = []
    try:
        r = sessie.get(sitemap_url, timeout=TIMEOUT, headers=HEADERS)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.content, "xml")

        # Sitemap-index: bevat verwijzingen naar andere sitemaps
        for sitemap_tag in soup.find_all("sitemap"):
            loc = sitemap_tag.find("loc")
            if loc:
                urls.extend(_haal_urls_uit_sitemap(sessie, loc.text.strip(), gezien))

        # Gewone sitemap: bevat pagina-URLs
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc:
                urls.append(loc.text.strip())

    except Exception as e:
        print(f"  Sitemap fout ({sitemap_url}): {e}")

    return urls


def _controleer_pagina(sessie: requests.Session, url: str) -> dict:
    resultaat = {
        "url": url,
        "status": None,
        "laadtijd": None,
        "fouten": [],
        "waarschuwingen": [],
        "links": [],
    }
    try:
        start = time.time()
        r = sessie.get(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
        laadtijd = round(time.time() - start, 2)
        resultaat["status"] = r.status_code
        resultaat["laadtijd"] = laadtijd

        if r.status_code >= 400:
            resultaat["fouten"].append(f"HTTP {r.status_code}")
            return resultaat

        if laadtijd > TRAAG_DREMPEL:
            resultaat["waarschuwingen"].append(f"Traag: {laadtijd}s")

        if "text/html" not in r.headers.get("Content-Type", ""):
            return resultaat

        soup = BeautifulSoup(r.text, "html.parser")

        # Meta-beschrijving
        meta = soup.find("meta", attrs={"name": "description"})
        if not meta or not meta.get("content", "").strip():
            resultaat["waarschuwingen"].append("Geen meta-beschrijving")

        # H1
        if not soup.find("h1"):
            resultaat["waarschuwingen"].append("Geen H1")

        # Afbeeldingen zonder alt-tekst
        imgs_zonder_alt = [
            img.get("src", "?") for img in soup.find_all("img")
            if not img.get("alt") and img.get("alt") != ""
        ]
        if imgs_zonder_alt:
            n = len(imgs_zonder_alt)
            resultaat["waarschuwingen"].append(
                f"{n} afbeelding{'en' if n != 1 else ''} zonder alt-tekst"
            )

        # Verzamel alle links
        for a in soup.find_all("a", href=True):
            href = _normaliseer(a["href"], url)
            if href.startswith("http"):
                resultaat["links"].append(href)

    except requests.exceptions.Timeout:
        resultaat["fouten"].append("Timeout")
    except requests.exceptions.ConnectionError:
        resultaat["fouten"].append("Verbinding mislukt")
    except Exception as e:
        resultaat["fouten"].append(f"Fout: {str(e)[:80]}")

    return resultaat


def audit():
    print(f"Site audit starten voor {STARTURL} ...")
    sessie = requests.Session()

    # Haal alle URLs op via de sitemap
    print(f"  Sitemap ophalen: {SITEMAP_URL}")
    sitemap_urls = _haal_urls_uit_sitemap(sessie, SITEMAP_URL)
    sitemap_urls = [u for u in sitemap_urls if _zelfde_domein(u)][:MAX_PAGINAS]

    if sitemap_urls:
        print(f"  {len(sitemap_urls)} pagina's gevonden in sitemap")
        wachtrij = sitemap_urls
    else:
        print("  Geen sitemap gevonden, start gewone crawl vanaf homepage")
        wachtrij = [STARTURL]

    bezocht = set()
    externe_links = set()
    alle_resultaten = []

    while wachtrij and len(bezocht) < MAX_PAGINAS:
        url = wachtrij.pop(0)
        if url in bezocht:
            continue
        bezocht.add(url)

        print(f"  [{len(bezocht):3d}/{len(wachtrij)+len(bezocht)}] {url}")
        res = _controleer_pagina(sessie, url)
        alle_resultaten.append(res)

        # Bij crawl-modus: volg ook gevonden links
        if not sitemap_urls:
            for link in res.get("links", []):
                if _zelfde_domein(link) and link not in bezocht:
                    wachtrij.append(link)
                elif not _zelfde_domein(link) and link.startswith("http"):
                    externe_links.add(link)

        time.sleep(0.5)  # Beleefd crawlen

    # Controleer externe links (alleen HTTP-status, geen crawl)
    externe_fouten = []
    if externe_links:
        print(f"\nExterne links controleren ({min(len(externe_links), MAX_EXTERN)})...")
        for url in list(externe_links)[:MAX_EXTERN]:
            try:
                r = sessie.head(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
                if r.status_code >= 400:
                    externe_fouten.append({"url": url, "status": r.status_code})
            except Exception:
                externe_fouten.append({"url": url, "status": "Fout"})
            time.sleep(0.3)

    n_fouten = sum(len(r["fouten"]) for r in alle_resultaten)
    n_warns  = sum(len(r["waarschuwingen"]) for r in alle_resultaten)

    output = {
        "datum": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "starturl": SITEMAP_URL if sitemap_urls else STARTURL,
        "paginas_gecontroleerd": len(alle_resultaten),
        "n_fouten": n_fouten,
        "n_waarschuwingen": n_warns,
        "resultaten": alle_resultaten,
        "externe_fouten": externe_fouten,
    }

    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nKlaar: {len(alle_resultaten)} pagina's, {n_fouten} fouten, {n_warns} waarschuwingen")
    print(f"Resultaat: {OUTPUT}")
    print("Draai nu generate_dashboard.py om het dashboard bij te werken.")


if __name__ == "__main__":
    audit()
