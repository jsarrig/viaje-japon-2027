#!/usr/bin/env python3
"""Registra a diario el precio de los vuelos del viaje a Japon.

Consulta Google Flights via SerpAPI (plan gratuito) y anade un registro por dia
a precios.json. Lo ejecuta GitHub Actions; la clave va en el secret SERPAPI_KEY.

Dos productos:
  - open-jaw: VLC -> KIX el 17/03 y NRT -> VLC el 31/03 (el plan)
  - tokio:    VLC -> NRT ida y vuelta 17/03 - 31/03 (la alternativa)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

ARCHIVO = "precios.json"
EXTRA_TRENES = 330  # sobrecoste en trenes de la ida y vuelta a Tokio (4 pax)

OPENJAW = [
    {"departure_id": "VLC", "arrival_id": "KIX", "date": "2027-03-17"},
    {"departure_id": "NRT", "arrival_id": "VLC", "date": "2027-03-31"},
]

BASE = dict(
    engine="google_flights",
    travel_class=1,
    adults=4,
    currency="EUR",
    hl="es",
    gl="es",
)


def consulta(api_key, **extra):
    params = dict(BASE, api_key=api_key, **extra)
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        print("SerpAPI devolvio HTTP %s: %s" % (e.code, detalle))
        return {}
    except Exception as e:  # red, timeout, JSON invalido
        print("Error consultando SerpAPI: %s" % e)
        return {}


def mejor_precio(datos):
    for clave in ("best_flights", "other_flights"):
        for vuelo in datos.get(clave) or []:
            if vuelo.get("price"):
                return vuelo["price"]
    return None


def main():
    api_key = (os.environ.get("SERPAPI_KEY") or "").strip()
    if not api_key:
        print("SERPAPI_KEY no configurada: no se registra nada.")
        return 0

    hoy = date.today().isoformat()
    forzado = (os.environ.get("FORZAR") or "").strip() in ("1", "true", "True") or "--force" in sys.argv

    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            serie = json.load(f)
        if not isinstance(serie, list):
            serie = []
    except (FileNotFoundError, json.JSONDecodeError):
        serie = []

    # Conserva el precio real de KLM.es si ya se habia anotado para hoy.
    klm_previo = None
    for registro in serie:
        if registro.get("fecha") == hoy and registro.get("klm") is not None:
            klm_previo = registro["klm"]

    # Idempotente: si ya hay dato de hoy no se gasta ninguna consulta.
    if not forzado:
        for registro in serie:
            if registro.get("fecha") == hoy and registro.get("openjaw") is not None:
                print("Ya hay registro de %s; nada que hacer." % hoy)
                return 0

    openjaw = consulta(
        api_key,
        type=3,
        multi_city_json=json.dumps(OPENJAW, separators=(",", ":")),
    )
    tokio = consulta(
        api_key,
        type=1,
        departure_id="VLC",
        arrival_id="NRT",
        outbound_date="2027-03-17",
        return_date="2027-03-31",
    )

    pistas = tokio.get("price_insights") or {}
    registro = {
        "fecha": hoy,
        "openjaw": mejor_precio(openjaw),
        "tokio": mejor_precio(tokio),
        "klm": klm_previo,
        "nivel": pistas.get("price_level"),
        "rango": pistas.get("typical_price_range"),
        "extra_trenes": EXTRA_TRENES,
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if registro["openjaw"] is None and registro["tokio"] is None:
        print("Sin precios validos; no se escribe nada.")
        print(json.dumps(openjaw.get("error") or tokio.get("error"), ensure_ascii=False))
        return 0

    serie = [r for r in serie if r.get("fecha") != registro["fecha"]]
    serie.append(registro)
    serie.sort(key=lambda r: str(r.get("fecha")))

    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(serie, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(json.dumps(registro, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
