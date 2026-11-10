#!/usr/bin/env python3
"""Hakee Mankolan koulun viikon ruokalistan eRuokalistalta (Aromi) ja kirjoittaa menu.json:n.
Vastaus tallennetaan myös raw.json:iin, jotta jäsennystä voi tarvittaessa korjata."""
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

OSOITE = ("https://aromimenu.cgisaas.fi/JyvaskylaAromieMenus/FI/Default/Ravintola/"
          "MankolaKOU/api/Common/Restaurant/RestaurantMeals")
RAVINTOLA_ID = "fda89f83-1a79-4cfc-9730-43dd04205aaa"
HKI = ZoneInfo("Europe/Helsinki")

PVM = re.compile(r"^(\d{4}-\d{2}-\d{2})")
OHITA = re.compile(r"allerg|diet|ingred|nutri|additive|label|icon|image|price|co2|carbon|energy|symbol", re.I)
EI_NIMI = ("day", "date", "lang", "user", "restaurant", "unit")


def paiva(s):
    """Päivämäärä merkkijonosta; Z-aikaleimat muunnetaan Suomen ajaksi."""
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d.astimezone(HKI) if d.tzinfo else d).date()
    except ValueError:
        m = PVM.match(s)
        return date.fromisoformat(m.group(1)) if m else None


def oma_pvm(d):
    for k, v in d.items():
        kl = k.lower()
        if isinstance(v, str) and PVM.match(v) and ("date" in kl or "day" in kl) \
                and "start" not in kl and "end" not in kl:
            return paiva(v)
    return None


def kaikki_pvm(node, acc=None):
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        p = oma_pvm(node)
        if p:
            acc.add(p)
        for v in node.values():
            kaikki_pvm(v, acc)
    elif isinstance(node, list):
        for v in node:
            kaikki_pvm(v, acc)
    return acc


def etsi_paivat(node, out):
    if isinstance(node, dict):
        avaimet = [(k, v) for k, v in node.items() if PVM.match(k)]
        if avaimet:
            for k, v in avaimet:
                out.append((paiva(k), v))
            return
        p = oma_pvm(node)
        if p and len(kaikki_pvm(node)) <= 1:
            out.append((p, node))
            return
        for v in node.values():
            etsi_paivat(v, out)
    elif isinstance(node, list):
        for v in node:
            etsi_paivat(v, out)


def nimi(d):
    for k, v in d.items():
        kl = k.lower()
        if isinstance(v, str) and v.strip() and not PVM.match(v) and \
                (kl in ("name", "nimi", "title", "text") or
                 (kl.endswith("name") and not any(x in kl for x in EI_NIMI))):
            return v.strip()
    return None


def lapsia(node):
    """Onko solmun alla nimettyjä alkioita (ohitettuja avaimia lukuun ottamatta)?"""
    if isinstance(node, list):
        return any(lapsia(v) for v in node)
    if isinstance(node, dict):
        if nimi(node):
            return True
        return any(lapsia(v) for k, v in node.items() if not OHITA.search(k))
    return False


def ruoat(node, ryhma=None, out=None):
    out = [] if out is None else out
    if isinstance(node, list):
        for v in node:
            ruoat(v, ryhma, out)
    elif isinstance(node, dict):
        n = nimi(node)
        lapset = [v for k, v in node.items()
                  if isinstance(v, (dict, list)) and not OHITA.search(k) and lapsia(v)]
        if n and not lapset:
            out.append({"ryhma": ryhma or "", "nimi": n})
        else:
            for v in lapset:
                ruoat(v, n or ryhma, out)
    return out


def jasenna(raaka, maanantai):
    loydetyt = []
    etsi_paivat(raaka, loydetyt)
    tulos = {}
    for p, solmu in loydetyt:
        if p is None:
            continue
        lista = tulos.setdefault(p, [])
        for r in ruoat(solmu):
            if r not in lista:
                lista.append(r)
    return [{"pvm": str(maanantai + timedelta(days=i)),
             "ruoat": tulos.get(maanantai + timedelta(days=i), [])} for i in range(5)]


def main():
    nyt = datetime.now(HKI)
    tanaan = nyt.date()
    ma = tanaan - timedelta(days=tanaan.weekday())
    if tanaan.weekday() >= 5:  # viikonloppuna näytetään tuleva viikko
        ma += timedelta(days=7)
    su = ma + timedelta(days=6)
    kysely = {"Id": RAVINTOLA_ID, "StartDate": f"{ma}T08:00:00.000Z", "EndDate": f"{su}T08:00:00.000Z"}
    pyynto = urllib.request.Request(
        OSOITE + "?" + urllib.parse.urlencode(kysely),
        headers={"User-Agent": "Mozilla/5.0 (ruokalistasivu)", "Accept": "application/json"})
    with urllib.request.urlopen(pyynto, timeout=30) as vastaus:
        raaka = json.loads(vastaus.read().decode("utf-8-sig"))
    with open("raw.json", "w", encoding="utf-8") as f:
        json.dump(raaka, f, ensure_ascii=False, indent=1)

    paivat = jasenna(raaka, ma)
    valmis = {"viikko": ma.isocalendar()[1], "maanantai": str(ma), "paivitetty": nyt.strftime("%-d.%-m. klo %H.%M"),
              "paivat": paivat}
    with open("menu.json", "w", encoding="utf-8") as f:
        json.dump(valmis, f, ensure_ascii=False, indent=1)

    for p in paivat:
        print(p["pvm"], len(p["ruoat"]), "ruokaa:", "; ".join(r["nimi"] for r in p["ruoat"])[:150])
    if not any(p["ruoat"] for p in paivat):
        print("VAROITUS: yhtään ruokaa ei löytynyt. Vastauksen alku:")
        print(json.dumps(raaka, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
