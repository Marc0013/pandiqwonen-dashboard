"""
PandIQ Zoektrends — haalt Google Trends op voor zoektermen in zoektermen.txt

Eenmalig installeren (in terminal):
    pip install pytrends

Gebruik:
    python trends.py

Zoektermen aanpassen: open zoektermen.txt in Kladblok
Resultaat wordt opgeslagen in data/trends.json
en is zichtbaar na het draaien van generate_dashboard.py
"""

import json
import time
from datetime import datetime
from pathlib import Path

BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
OUTPUT        = DATA_DIR / "trends.json"
KEYWORDS_FILE = BASE_DIR / "zoektermen.txt"
DATA_DIR.mkdir(exist_ok=True)


def lees_zoektermen() -> list:
    if not KEYWORDS_FILE.exists():
        print(f"Bestand niet gevonden: {KEYWORDS_FILE}")
        return []
    regels = KEYWORDS_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [r.strip() for r in regels if r.strip() and not r.startswith("#")]


def haal_trends_op(termen: list) -> list:
    from pytrends.request import TrendReq
    pytrends = TrendReq(hl="nl-NL", tz=60)
    resultaten = []

    # pytrends accepteert max 5 termen tegelijk
    for i in range(0, len(termen), 5):
        batch = termen[i:i + 5]
        print(f"  Ophalen: {', '.join(batch)}")
        try:
            pytrends.build_payload(batch, timeframe="today 3-m", geo="NL")
            df = pytrends.interest_over_time()

            for term in batch:
                if df.empty or term not in df.columns:
                    resultaten.append({
                        "term": term, "richting": "onbekend",
                        "verandering": 0, "waarden": [],
                        "piek": 0, "huidig": 0, "fout": "Geen data ontvangen",
                    })
                    continue

                waarden = df[term].tolist()

                # Trend: laatste 2 weken vs 2 weken daarvoor
                if len(waarden) >= 4:
                    recent = sum(waarden[-2:]) / 2
                    vorig  = sum(waarden[-4:-2]) / 2
                    verandering = round(((recent - vorig) / vorig) * 100) if vorig > 0 else 0
                else:
                    verandering = 0

                if verandering > 5:
                    richting = "op"
                elif verandering < -5:
                    richting = "neer"
                else:
                    richting = "stabiel"

                max_waarde = max(waarden) if waarden else 1
                genormaliseerd = [round(v / max_waarde * 100) for v in waarden]

                resultaten.append({
                    "term": term,
                    "richting": richting,
                    "verandering": verandering,
                    "waarden": genormaliseerd,
                    "piek": int(max(waarden)) if waarden else 0,
                    "huidig": int(waarden[-1]) if waarden else 0,
                })

            time.sleep(3)  # Rate limit vermijden

        except Exception as e:
            print(f"  Fout bij ophalen: {e}")
            for term in batch:
                resultaten.append({
                    "term": term, "richting": "onbekend",
                    "verandering": 0, "waarden": [],
                    "piek": 0, "huidig": 0, "fout": str(e)[:100],
                })

    return resultaten


def main():
    termen = lees_zoektermen()
    if not termen:
        print("Geen zoektermen gevonden. Controleer zoektermen.txt")
        return

    print(f"Trends ophalen voor {len(termen)} zoektermen (Google NL)...")
    resultaten = haal_trends_op(termen)

    output = {
        "datum": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "periode": "Laatste 3 maanden · Nederland",
        "termen": resultaten,
    }

    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nKlaar! {len(resultaten)} termen opgeslagen in {OUTPUT}")
    print("Draai nu generate_dashboard.py om het dashboard bij te werken.")


if __name__ == "__main__":
    main()
