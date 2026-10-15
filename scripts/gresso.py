#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gresso: crea y actualiza el HTML de seguimiento sin que su contenido pase por el modelo.

    python gresso.py crear  <salida.html> [--titulo T] [--subtitulo S]   < datos.json
    python gresso.py ver    <salida.html>
    python gresso.py estado <salida.html> t3=hecho t4=haciendo "t5=bloqueado:falta la clave"
    python gresso.py parte  <salida.html> "Dónde voy, en dos o tres líneas"
    python gresso.py anadir <salida.html> --fase "Nombre de la fase"      < tareas.json

En crear y anadir, --datos archivo.json sustituye a la entrada estándar. La entrada se lee
en UTF-8 y, si no lo es, en cp1252, así que los acentos llegan bien desde Git Bash y PowerShell.

datos.json  -> {"titulo":..., "subtitulo":..., "parte":..., "fases":[{"nombre":...,
                "tareas":[{"id":"t1","texto":"...","estado":"pendiente","nota":"...","peso":1}]}]}
tareas.json -> la lista de tareas sola, con la misma forma.

Todo comando reescribe la fecha y la hora de arriba, que es lo que le dice al lector
si lo que está mirando es de ahora.
"""

import json
import os
import re
import sys
from datetime import datetime

ESTADOS = ("pendiente", "haciendo", "hecho", "bloqueado", "descartado")
MARCA = re.compile(
    r'(<script id="gresso-datos" type="application/json">)(.*?)(</script>)',
    re.DOTALL,
)


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def muere(mensaje):
    sys.stderr.write("gresso: " + mensaje + "\n")
    raise SystemExit(1)


def decodificar(bruto):
    # En Windows, sys.stdin se lee en cp1252 y convierte "Revisión" en "RevisiÃ³n".
    # Se leen los bytes y se prueba UTF-8 primero, que es lo que manda Git Bash.
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return bruto.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def leer_entrada(archivo=None):
    if archivo:
        if not os.path.exists(archivo):
            muere("no existe el archivo de datos %s" % archivo)
        with open(archivo, "rb") as f:
            bruto = f.read()
    else:
        bruto = sys.stdin.buffer.read()
    crudo = decodificar(bruto).strip()
    if not crudo:
        muere("no llegaron datos: pásalos por la entrada estándar o con --datos archivo.json")
    try:
        return json.loads(crudo)
    except ValueError as e:
        muere("el JSON de entrada no es válido: %s" % e)


def plantilla_por_defecto():
    aqui = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(aqui), "references", "plantilla.html")


def numerar(fases):
    """Pone id a toda tarea que no lo traiga, y normaliza el estado.

    Un id que ya existe NO cambia nunca: el agente los recuerda para marcar tareas, y si
    al anadir una en medio se corrieran los de detras, marcaria la que no es. Las nuevas
    reciben el siguiente numero libre, vayan en la fase que vayan.
    """
    todas = [t for fase in fases for t in fase.get("tareas", [])]
    mayor = 0
    for t in todas:
        tid = str(t.get("id") or "").strip()
        if tid[:1] == "t" and tid[1:].isdigit():
            mayor = max(mayor, int(tid[1:]))
    vistos = set()
    for t in todas:
        tid = str(t.get("id") or "").strip()
        if not tid or tid in vistos:
            mayor += 1
            tid = "t%d" % mayor
        t["id"] = tid
        vistos.add(tid)
        if t.get("estado") not in ESTADOS:
            t["estado"] = "pendiente"
    return fases


def incrustar(html, datos):
    datos["actualizado"] = ahora()
    # El JSON vive dentro de un <script>: un "</" suelto cerraria la etiqueta antes de tiempo.
    crudo = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    if not MARCA.search(html):
        muere("ese archivo no es un seguimiento de Gresso (falta el bloque gresso-datos)")
    return MARCA.sub(lambda m: m.group(1) + crudo + m.group(3), html, count=1)


def extraer(ruta):
    if not os.path.exists(ruta):
        muere("no existe %s" % ruta)
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    m = MARCA.search(html)
    if not m:
        muere("ese archivo no es un seguimiento de Gresso (falta el bloque gresso-datos)")
    return html, json.loads(m.group(2).replace("<\\/", "</"))


def guardar(ruta, html, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(incrustar(html, datos))
    print(os.path.abspath(ruta))


def cuentas(datos):
    todas = [t for f in datos.get("fases", []) for t in f.get("tareas", [])]
    utiles = [t for t in todas if t.get("estado") != "descartado"]
    hechas = [t for t in utiles if t.get("estado") == "hecho"]
    # El porcentaje va por peso, igual que lo calcula la página: si no, la terminal y el
    # navegador dan cifras distintas para el mismo seguimiento.
    total = sum(peso(t) for t in utiles)
    hecho = sum(peso(t) for t in hechas)
    pct = int(round(hecho * 100.0 / total)) if total else 0
    return todas, utiles, hechas, pct


def peso(tarea):
    p = tarea.get("peso")
    return p if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0 else 1


# --------------------------------------------------------------------------- crear
def cmd_crear(ruta, resto):
    titulo = subtitulo = plantilla = archivo = None
    i = 0
    while i < len(resto):
        if resto[i] == "--datos" and i + 1 < len(resto):
            archivo = resto[i + 1]; i += 2
        elif resto[i] == "--titulo" and i + 1 < len(resto):
            titulo = resto[i + 1]; i += 2
        elif resto[i] == "--subtitulo" and i + 1 < len(resto):
            subtitulo = resto[i + 1]; i += 2
        elif resto[i] == "--plantilla" and i + 1 < len(resto):
            plantilla = resto[i + 1]; i += 2
        else:
            i += 1

    datos = leer_entrada(archivo)
    if titulo:
        datos["titulo"] = titulo
    if subtitulo:
        datos["subtitulo"] = subtitulo
    datos.setdefault("titulo", "Seguimiento")
    datos["fases"] = numerar(datos.get("fases", []))

    origen = plantilla or plantilla_por_defecto()
    if not os.path.exists(origen):
        muere("no encuentro la plantilla en %s" % origen)
    with open(origen, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TITULO__", datos["titulo"])

    carpeta = os.path.dirname(os.path.abspath(ruta))
    if carpeta and not os.path.isdir(carpeta):
        os.makedirs(carpeta)
    guardar(ruta, html, datos)


# ----------------------------------------------------------------------------- ver
def cmd_ver(ruta):
    html, datos = extraer(ruta)
    todas, utiles, hechas, pct = cuentas(datos)
    print("%s | %d%% (%d de %d) | actualizado %s"
          % (datos.get("titulo", "Seguimiento"), pct, len(hechas), len(utiles),
             datos.get("actualizado", "?")))
    for fase in datos.get("fases", []):
        print("\n[%s]" % fase.get("nombre", "Tareas"))
        for t in fase.get("tareas", []):
            nota = ("  (%s)" % t["nota"]) if t.get("nota") else ""
            print("  %-6s %-11s %s%s" % (t.get("id", "?"), t.get("estado", "pendiente"),
                                         t.get("texto", ""), nota))


# -------------------------------------------------------------------------- estado
def cmd_estado(ruta, pares):
    if not pares:
        muere('dime qué cambiar, por ejemplo: estado seguimiento.html t3=hecho')
    html, datos = extraer(ruta)
    indice = {t.get("id"): t for f in datos.get("fases", []) for t in f.get("tareas", [])}
    tocadas = 0
    for par in pares:
        if "=" not in par:
            muere('"%s" no tiene la forma id=estado' % par)
        tid, valor = par.split("=", 1)
        nota = None
        if ":" in valor:
            valor, nota = valor.split(":", 1)
        tid, valor = tid.strip(), valor.strip()
        if tid not in indice:
            muere('no hay ninguna tarea con id "%s" (mira "gresso.py ver")' % tid)
        if valor not in ESTADOS:
            muere('"%s" no es un estado; los válidos son: %s' % (valor, ", ".join(ESTADOS)))
        indice[tid]["estado"] = valor
        if nota is not None:
            nota = nota.strip()
            if nota:
                indice[tid]["nota"] = nota
            else:
                indice[tid].pop("nota", None)
        tocadas += 1
    guardar(ruta, html, datos)
    _, utiles, hechas, pct = cuentas(datos)
    print("%d tarea(s) cambiada(s) | %d%% (%d de %d)" % (tocadas, pct, len(hechas), len(utiles)))


# --------------------------------------------------------------------------- parte
def cmd_parte(ruta, texto):
    html, datos = extraer(ruta)
    datos["parte"] = texto
    guardar(ruta, html, datos)


# -------------------------------------------------------------------------- anadir
def cmd_anadir(ruta, resto):
    nombre = archivo = None
    i = 0
    while i < len(resto):
        if resto[i] == "--fase" and i + 1 < len(resto):
            nombre = resto[i + 1]; i += 2
        elif resto[i] == "--datos" and i + 1 < len(resto):
            archivo = resto[i + 1]; i += 2
        else:
            i += 1
    nuevas = leer_entrada(archivo)
    if isinstance(nuevas, dict):
        nuevas = nuevas.get("tareas", [])
    if not isinstance(nuevas, list) or not nuevas:
        muere("esperaba una lista de tareas por la entrada estándar")

    html, datos = extraer(ruta)
    fases = datos.setdefault("fases", [])
    destino = None
    if nombre:
        for f in fases:
            if f.get("nombre") == nombre:
                destino = f
                break
        if destino is None:
            destino = {"nombre": nombre, "tareas": []}
            fases.append(destino)
    else:
        if not fases:
            fases.append({"nombre": "Tareas", "tareas": []})
        destino = fases[-1]
    destino.setdefault("tareas", []).extend(nuevas)
    datos["fases"] = numerar(fases)
    guardar(ruta, html, datos)
    _, utiles, hechas, pct = cuentas(datos)
    print("%d tarea(s) añadida(s) | %d%% (%d de %d)" % (len(nuevas), pct, len(hechas), len(utiles)))


def main():
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        raise SystemExit(1)
    orden, ruta, resto = sys.argv[1], sys.argv[2], sys.argv[3:]
    if orden == "crear":
        cmd_crear(ruta, resto)
    elif orden == "ver":
        cmd_ver(ruta)
    elif orden == "estado":
        cmd_estado(ruta, resto)
    elif orden == "parte":
        if not resto:
            muere("dime el texto del parte")
        cmd_parte(ruta, " ".join(resto))
    elif orden == "anadir":
        cmd_anadir(ruta, resto)
    else:
        muere('orden desconocida "%s" (crear, ver, estado, parte, anadir)' % orden)


if __name__ == "__main__":
    main()
