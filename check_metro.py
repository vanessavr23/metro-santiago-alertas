#!/usr/bin/env python3
"""Monitor del estado de la red de Metro de Santiago.

Consulta el endpoint publico que usa metro.cl, compara con el estado guardado
en la ejecucion anterior y envia alertas a Telegram y/o Discord solo cuando
algo cambia (cierre, reapertura o cambio de estado de una linea o estacion).

Solo usa la libreria estandar de Python (3.10+): no requiere pip install.

Uso:
    python check_metro.py                  # verificar y alertar si hay cambios
    python check_metro.py --consultar      # mostrar el estado actual (no alerta ni guarda)
    python check_metro.py --probar-envio   # enviar un mensaje de prueba a los canales configurados

Variables de entorno (opcionales; sin ellas los mensajes se imprimen en consola):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL
    METRO_ESTADO_ARCHIVO   ruta del archivo de estado (por defecto: estado.json)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

METRO_API_URL = "https://www.metro.cl/api/estadoRedDetalle.php"
METRO_WEB_URL = "https://www.metro.cl/el-viaje/estado-red"
ESTADO_NORMAL = "1"
FALLOS_PARA_AVISAR = 3  # consultas fallidas seguidas antes de avisar
USER_AGENT = "metro-santiago-alertas/1.0 (+https://github.com/vanessavr23/metro-santiago-alertas)"
TELEGRAM_LIMITE = 4000  # Telegram acepta 4096 caracteres; se deja margen
DISCORD_LIMITE = 1900  # Discord acepta 2000

NOMBRES_LINEA = {
    "l1": "Línea 1", "l2": "Línea 2", "l3": "Línea 3", "l4": "Línea 4",
    "l4a": "Línea 4A", "l5": "Línea 5", "l6": "Línea 6", "l7": "Línea 7",
}


class ErrorConsulta(Exception):
    """No se pudo obtener o interpretar el estado de la red."""


# --------------------------------------------------------------------------- #
# Consulta y normalizacion
# --------------------------------------------------------------------------- #
def descargar_estado(url: str = METRO_API_URL, intentos: int = 3, timeout: int = 15) -> dict:
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                cuerpo = resp.read().decode("utf-8")
            return json.loads(cuerpo)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            ultimo_error = e
            if intento < intentos:
                time.sleep(3 * intento)
    raise ErrorConsulta(f"No se pudo consultar {url}: {ultimo_error}")


def normalizar(data: dict) -> dict:
    """Convierte la respuesta de Metro en un snapshot plano y estable."""
    if not isinstance(data, dict) or not data:
        raise ErrorConsulta("Respuesta vacía o con formato inesperado")
    lineas: dict[str, dict] = {}
    estaciones: dict[str, dict] = {}
    for id_linea, linea in data.items():
        if not isinstance(linea, dict) or "estaciones" not in linea:
            raise ErrorConsulta(f"La línea {id_linea!r} no tiene el formato esperado")
        lineas[id_linea] = {
            "nombre": NOMBRES_LINEA.get(id_linea, id_linea.upper()),
            "estado": str(linea.get("estado", "")),
            "texto": (linea.get("mensaje_app") or "").strip(),
            "mensaje": (linea.get("mensaje") or "").strip(),
        }
        for est in linea["estaciones"]:
            clave = f"{id_linea}:{est.get('codigo') or est.get('nombre')}"
            estaciones[clave] = {
                "nombre": (est.get("nombre") or "").strip(),
                "linea": id_linea,
                "estado": str(est.get("estado", "")),
                "texto": (est.get("descripcion_app") or est.get("descripcion") or "").strip(),
                "descripcion": (est.get("descripcion") or "").strip(),
                "mensaje": (est.get("mensaje") or "").strip(),
            }
    if not estaciones:
        raise ErrorConsulta("La respuesta no contiene estaciones")
    return {"lineas": lineas, "estaciones": estaciones}


# --------------------------------------------------------------------------- #
# Comparacion
# --------------------------------------------------------------------------- #
def comparar(anterior: dict, actual: dict) -> list[dict]:
    """Devuelve la lista de cambios relevantes entre dos snapshots."""
    cambios: list[dict] = []
    for tipo in ("lineas", "estaciones"):
        prev_items = anterior.get(tipo, {})
        for clave, item in actual[tipo].items():
            prev = prev_items.get(clave)
            prev_estado = prev["estado"] if prev else ESTADO_NORMAL
            if prev_estado == item["estado"]:
                continue
            if item["estado"] == ESTADO_NORMAL:
                accion = "reabierta"
            elif prev_estado == ESTADO_NORMAL:
                accion = "incidencia"
            else:
                accion = "cambio"
            cambios.append({"tipo": tipo, "clave": clave, "accion": accion,
                            "antes": prev_estado, **item})
    return cambios


def registrar_codigos(estado_guardado: dict, actual: dict) -> None:
    """Guarda que texto acompaña a cada código, para aprender su significado."""
    vistos = estado_guardado.setdefault("codigos_vistos", {})
    for item in actual["estaciones"].values():
        vistos.setdefault(item["estado"], item["descripcion"] or item["texto"])


# --------------------------------------------------------------------------- #
# Mensajes
# --------------------------------------------------------------------------- #
def hora_chile() -> str:
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("America/Santiago"))
    except Exception:  # sin base de zonas horarias: UTC-3 aproximado
        ahora = datetime.now(timezone(timedelta(hours=-3)))
    return ahora.strftime("%d-%m-%Y %H:%M")


def formatear_cambios(cambios: list[dict]) -> str:
    e = html.escape
    incidencias = [c for c in cambios if c["accion"] in ("incidencia", "cambio")]
    reaperturas = [c for c in cambios if c["accion"] == "reabierta"]
    partes = [f"🚇 <b>Metro de Santiago</b> · {e(hora_chile())}"]

    def linea_de(c: dict) -> str:
        if c["tipo"] == "lineas":
            titulo = f"<b>{e(c['nombre'])}</b> (línea completa)"
        else:
            titulo = f"<b>{e(c['nombre'])}</b> · {e(NOMBRES_LINEA.get(c['linea'], c['linea']))}"
        detalle = c["texto"] or f"estado {c['estado']}"
        texto = f"{titulo}: {e(detalle)}"
        if c["mensaje"]:
            texto += f"\n   <i>{e(c['mensaje'])}</i>"
        return texto

    if incidencias:
        partes.append("\n⚠️ <b>Incidencias</b>")
        partes += [f"• {linea_de(c)}" for c in incidencias]
    if reaperturas:
        partes.append("\n✅ <b>Normalizado</b>")
        partes += [f"• {linea_de(c)}" for c in reaperturas]
    partes.append(f'\n<a href="{METRO_WEB_URL}">Ver estado en metro.cl</a>')
    return "\n".join(partes)


def resumen_actual(actual: dict) -> str:
    filas = []
    for id_linea, linea in actual["lineas"].items():
        anormales = [s for s in actual["estaciones"].values()
                     if s["linea"] == id_linea and s["estado"] != ESTADO_NORMAL]
        total = sum(1 for s in actual["estaciones"].values() if s["linea"] == id_linea)
        marca = "✅" if linea["estado"] == ESTADO_NORMAL and not anormales else "⚠️"
        filas.append(f"{marca} {linea['nombre']}: {linea['texto'] or linea['estado']} "
                     f"({total - len(anormales)}/{total} estaciones normales)")
        for s in anormales:
            filas.append(f"     - {s['nombre']}: {s['texto'] or s['estado']} {s['mensaje']}".rstrip())
    return "\n".join(filas)


def dividir(texto: str, limite: int) -> list[str]:
    bloques, actual = [], ""
    for linea in texto.split("\n"):
        if actual and len(actual) + len(linea) + 1 > limite:
            bloques.append(actual)
            actual = ""
        actual = f"{actual}\n{linea}" if actual else linea
    if actual:
        bloques.append(actual)
    return bloques


# --------------------------------------------------------------------------- #
# Envio
# --------------------------------------------------------------------------- #
def _post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as err:
        detalle = err.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {err.code}: {detalle}") from None


def html_a_markdown_discord(texto: str) -> str:
    import re
    texto = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"[\2](\1)", texto)
    texto = texto.replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*")
    return html.unescape(texto)


def enviar(mensaje_html: str) -> list[str]:
    """Envía a todos los canales configurados. Devuelve los canales usados."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    discord = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    canales = []
    if token and chat_id:
        for bloque in dividir(mensaje_html, TELEGRAM_LIMITE):
            _post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                       {"chat_id": chat_id, "text": bloque, "parse_mode": "HTML",
                        "disable_web_page_preview": True})
        canales.append("telegram")
    if discord:
        for bloque in dividir(html_a_markdown_discord(mensaje_html), DISCORD_LIMITE):
            _post_json(discord, {"content": bloque})
        canales.append("discord")
    if not canales:
        print("[sin canales configurados] Mensaje que se habría enviado:\n" + mensaje_html)
    return canales


# --------------------------------------------------------------------------- #
# Estado persistente
# --------------------------------------------------------------------------- #
def cargar_estado(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Aviso: no se pudo leer {ruta}; se tomará como primera ejecución", file=sys.stderr)
        return {}


def guardar_estado(ruta: Path, estado: dict) -> None:
    ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


# --------------------------------------------------------------------------- #
# Flujo principal
# --------------------------------------------------------------------------- #
def verificar(ruta_estado: Path) -> int:
    guardado = cargar_estado(ruta_estado)
    fallos_previos = int(guardado.get("fallos_consecutivos", 0))

    try:
        actual = normalizar(descargar_estado())
    except ErrorConsulta as err:
        fallos = fallos_previos + 1
        print(f"Error ({fallos} seguido/s): {err}", file=sys.stderr)
        guardado["fallos_consecutivos"] = fallos
        guardar_estado(ruta_estado, guardado)
        if fallos == FALLOS_PARA_AVISAR:
            try:
                enviar("🛠️ <b>Monitor Metro</b>: no puedo consultar el estado de la red desde hace "
                       f"{fallos} intentos seguidos.\n<i>{html.escape(str(err))[:300]}</i>")
            except Exception as e:  # el aviso es secundario
                print(f"No se pudo enviar el aviso de falla: {e}", file=sys.stderr)
            return 1  # marca la ejecución en rojo una sola vez (GitHub avisa por correo)
        return 0

    primera_vez = "estaciones" not in guardado
    cambios = [] if primera_vez else comparar(guardado, actual)

    if cambios:
        mensaje = formatear_cambios(cambios)
        try:
            canales = enviar(mensaje)
        except Exception as err:
            # No se guarda el estado: el próximo ciclo reintenta el envío.
            print(f"Error al enviar la alerta: {err}", file=sys.stderr)
            return 1
        print(f"{len(cambios)} cambio(s) notificados por: {', '.join(canales) or 'consola'}")
    elif primera_vez:
        print("Primera ejecución: estado base guardado, sin alertas.")
    else:
        print("Sin cambios.")

    if fallos_previos >= FALLOS_PARA_AVISAR:
        try:
            enviar("🛠️ <b>Monitor Metro</b>: la consulta volvió a funcionar.")
        except Exception as e:
            print(f"No se pudo enviar el aviso de recuperación: {e}", file=sys.stderr)

    nuevo = {**actual, "codigos_vistos": guardado.get("codigos_vistos", {}),
             "fallos_consecutivos": 0}
    registrar_codigos(nuevo, actual)
    if cambios or primera_vez:
        nuevo["ultimo_cambio"] = hora_chile()
    elif "ultimo_cambio" in guardado:
        nuevo["ultimo_cambio"] = guardado["ultimo_cambio"]
    guardar_estado(ruta_estado, nuevo)
    print(resumen_actual(actual))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--consultar", action="store_true", help="mostrar el estado actual sin alertar ni guardar")
    p.add_argument("--probar-envio", action="store_true", help="enviar un mensaje de prueba")
    p.add_argument("--estado", default=os.getenv("METRO_ESTADO_ARCHIVO", "estado.json"),
                   help="archivo donde se guarda el último estado")
    args = p.parse_args(argv)

    if args.probar_envio:
        canales = enviar(f"✅ <b>Monitor Metro</b>: mensaje de prueba ({html.escape(hora_chile())}).")
        print(f"Prueba enviada por: {', '.join(canales) or 'consola'}")
        return 0
    if args.consultar:
        try:
            print(resumen_actual(normalizar(descargar_estado())))
        except ErrorConsulta as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1
        return 0
    return verificar(Path(args.estado))


if __name__ == "__main__":
    sys.exit(main())
