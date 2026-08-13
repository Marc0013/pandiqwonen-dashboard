"""
PandIQ Mail Samenvatting — stuurt dagelijks een e-mail met dashboard-update.

Vereiste omgevingsvariabelen (GitHub Secrets):
  MAIL_FROM     — Gmail-adres waarvandaan verstuurd wordt
  MAIL_PASSWORD — Gmail App-wachtwoord (niet je gewone wachtwoord)
  MAIL_TO       — E-mailadres waarnaartoe verstuurd wordt

Zie SETUP.md voor instructies om deze in te stellen.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"

DASHBOARD_URL = "https://marc0013.github.io/pandiqwonen-dashboard/"


def lees_json(bestand: str) -> dict:
    pad = DATA_DIR / bestand
    if not pad.exists():
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except Exception:
        return {}


def maak_html(audit: dict, trends: dict) -> str:
    datum = datetime.now().strftime("%d %B %Y")

    # --- Audit samenvatting ---
    if audit:
        n_paginas = audit.get("paginas_gecontroleerd", 0)
        n_fouten  = audit.get("n_fouten", 0) + len(audit.get("externe_fouten", []))
        n_warns   = audit.get("n_waarschuwingen", 0)

        fout_kleur  = "#c62828" if n_fouten  else "#2e7d32"
        warn_kleur  = "#e65100" if n_warns   else "#2e7d32"
        fout_tekst  = f"{n_fouten} fout{'en' if n_fouten != 1 else ''}"  if n_fouten else "geen fouten"
        warn_tekst  = f"{n_warns} waarschuwing{'en' if n_warns != 1 else ''}" if n_warns else "geen waarschuwingen"

        audit_html = f"""
        <tr>
          <td style="padding:16px 24px;border-bottom:1px solid #f0f0f0">
            <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#888;margin-bottom:10px">Site Audit — wonen.pandiq.nl</div>
            <table width="100%"><tr>
              <td style="text-align:center;padding:8px">
                <div style="font-size:22px;font-weight:700;color:#1a1a2e">{n_paginas}</div>
                <div style="font-size:12px;color:#888">pagina's</div>
              </td>
              <td style="text-align:center;padding:8px">
                <div style="font-size:22px;font-weight:700;color:{fout_kleur}">{n_fouten}</div>
                <div style="font-size:12px;color:#888">{fout_tekst}</div>
              </td>
              <td style="text-align:center;padding:8px">
                <div style="font-size:22px;font-weight:700;color:{warn_kleur}">{n_warns}</div>
                <div style="font-size:12px;color:#888">{warn_tekst}</div>
              </td>
            </tr></table>
          </td>
        </tr>"""
    else:
        audit_html = ""

    # --- Trends samenvatting ---
    trends_rijen = ""
    if trends and trends.get("termen"):
        termen = [t for t in trends["termen"] if not t.get("fout") and t.get("waarden")]
        termen_gesorteerd = sorted(termen, key=lambda t: abs(t.get("verandering", 0)), reverse=True)
        for t in termen_gesorteerd[:5]:
            richting   = t.get("richting", "stabiel")
            verandering = t.get("verandering", 0)
            if richting == "op":
                pijl, kleur, teken = "↑", "#2e7d32", f"+{verandering}%"
            elif richting == "neer":
                pijl, kleur, teken = "↓", "#c62828", f"{verandering}%"
            else:
                pijl, kleur, teken = "→", "#888", "stabiel"
            trends_rijen += f"""
            <tr style="border-bottom:1px solid #f5f5f5">
              <td style="padding:8px 12px;font-size:13px;color:#1a1a2e">{t['term']}</td>
              <td style="padding:8px 12px;font-size:15px;font-weight:700;color:{kleur};text-align:right">{pijl} {teken}</td>
            </tr>"""

    trends_html = f"""
        <tr>
          <td style="padding:16px 24px">
            <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#888;margin-bottom:10px">Zoektrends — Google NL</div>
            <table width="100%" style="border-collapse:collapse">{trends_rijen}</table>
            <div style="font-size:11px;color:#bbb;margin-top:8px">Bron: Google Trends · {trends.get('periode','')}</div>
          </td>
        </tr>""" if trends_rijen else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:32px 0">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0" style="background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">

        <!-- Header -->
        <tr>
          <td style="background:#1a1a2e;padding:20px 24px">
            <div style="font-size:18px;font-weight:600;color:white">PandIQ Wonen — Dashboard Update</div>
            <div style="font-size:13px;color:rgba(255,255,255,.6);margin-top:4px">{datum}</div>
          </td>
        </tr>

        <!-- Audit -->
        {audit_html}

        <!-- Trends -->
        {trends_html}

        <!-- Knop -->
        <tr>
          <td style="padding:20px 24px;border-top:1px solid #f0f0f0;text-align:center">
            <a href="{DASHBOARD_URL}"
               style="display:inline-block;background:#1a1a2e;color:white;padding:12px 28px;
                      border-radius:6px;text-decoration:none;font-weight:600;font-size:14px">
              Bekijk het volledige dashboard →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 24px;text-align:center;font-size:12px;color:#bbb;border-top:1px solid #f0f0f0">
            Automatisch gegenereerd door PandIQ Dashboard
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body></html>"""


def stuur_mail(html: str):
    mail_from     = os.environ.get("MAIL_FROM", "")
    mail_password = os.environ.get("MAIL_PASSWORD", "")
    mail_to       = os.environ.get("MAIL_TO", "")

    if not all([mail_from, mail_password, mail_to]):
        print("E-mail variabelen niet ingesteld — mail overgeslagen.")
        print("Zie SETUP.md voor instructies.")
        return

    datum = datetime.now().strftime("%d-%m-%Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PandIQ Dashboard — update {datum}"
    msg["From"]    = f"PandIQ Dashboard <{mail_from}>"
    msg["To"]      = mail_to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mail_from, mail_password)
        smtp.sendmail(mail_from, mail_to, msg.as_string())

    print(f"E-mail verstuurd naar {mail_to}")


def main():
    audit  = lees_json("site_audit.json")
    trends = lees_json("trends.json")
    html   = maak_html(audit, trends)
    stuur_mail(html)


if __name__ == "__main__":
    main()
