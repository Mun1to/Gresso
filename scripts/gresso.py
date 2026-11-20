#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gresso: crea y actualiza el HTML de seguimiento sin que su contenido pase por el modelo.

    python gresso.py crear  <salida.html> [--titulo T] [--subtitulo S] [--proyecto P]  < datos.json
    python gresso.py ver    <salida.html>
    python gresso.py estado <salida.html> t3=hecho t4=haciendo "t5=bloqueado:falta la clave"
    python gresso.py estado <salida.html> t6=ya t7=noya
    python gresso.py parte  <salida.html> "Dónde voy, en dos o tres líneas"
    python gresso.py anadir <salida.html> --fase "Nombre de la fase"      < tareas.json
    python gresso.py renovar <salida.html> [--marca marca.json]
    python gresso.py decisiones <salida.html>

crear y renovar admiten --marca marca.json: {"nombre":...,"logo":...,"logoOscuro":...,
"mascota":...,"pixelada":true,"colores":{"acento":"#3E5BA9",...},"oscuro":{...},"letra":...,
"letraTitulos":...}. Logo y mascota son un archivo, un <svg> o un data:, y quedan dentro de la
página. renovar pasa una página a la plantilla actual sin perder datos y deja copia en .bak.

En crear y anadir, --datos archivo.json sustituye a la entrada estándar. La entrada se lee
en UTF-8 y, si no lo es, en cp1252, así que los acentos llegan bien desde Git Bash. La tubería de PowerShell 5.1 los
convierte en ? antes de llegar: allí, --datos.

datos.json  -> {"titulo":..., "subtitulo":..., "parte":..., "fases":[{"nombre":...,
                "tareas":[{"id":"t1","texto":"...","estado":"pendiente","nota":"...","peso":1}]}]}
tareas.json -> la lista de tareas sola, con la misma forma.

Una tarea de quien lee lleva además "quien":"tu", y puede traer "porque", "pasos":[...],
"acciones":[{"texto":...,"url":...} o {"texto":...,"copiar":...}] y "dime".
Con "ya":true es de las que tiene que hacer ya, sí o sí: solo puede hacerla quien lee y algo se
para si no la hace. Pasa delante de todo lo suyo en la tarjeta de arriba. estado tN=ya la sube
y tN=noya la baja; al pasar a hecho deja la tarjeta a la siguiente.
Una decisión lleva "decision":{"opciones":[{"texto":...,"detalle":...,"recomendada":true,
"porque":...,"malo":...,"bueno":...,"cuesta":...,"noHace":...,"icono":...}],"siNoDices":...,
"varias":false}. La página la enseña en la tarjeta de arriba, con las opciones como botones, y
decisiones imprime las abiertas, con su letra y en el orden de la página, para preguntarlas
también por otro sitio (el móvil) con los mismos números.

Toda orden que cambia algo escribe también <salida.html>.version.js: la pestaña abierta lo
pide cada pocos segundos y se pone al día sola, sin pulsar F5.
"""

import base64
import html as escape_html
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime

ESTADOS = ("pendiente", "haciendo", "hecho", "bloqueado", "descartado")
# Lo que le toca a quien lee y no puede esperar pasa delante. Más de tres a la vez ya no es urgente.
MAX_YA = 3
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


def avisar_si_perdio_tildes(texto):
    # PowerShell 5.1 convierte lo que no es ASCII en "?" ANTES de que llegue aquí, y ya no se puede recuperar.
    if re.search(r"[^\W\d_]\?[^\W\d_]", texto) and "://" not in texto:
        sys.stderr.write("gresso: aviso: hay un \"?\" entre dos letras: parece que la tubería se ha comido tildes o eñes. "
                         "Escríbelo en un archivo y pásalo con --datos.\n")


def leer_entrada(archivo=None):
    if archivo:
        if not os.path.exists(archivo):
            muere("no existe el archivo de datos %s" % archivo)
        with open(archivo, "rb") as f:
            bruto = f.read()
    else:
        bruto = sys.stdin.buffer.read()
    crudo = decodificar(bruto).strip()
    if not archivo:
        avisar_si_perdio_tildes(crudo)
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
        # Una decisión sin opciones no se puede contestar en la página: mejor saberlo ahora.
        if t.get("decision") is not None and not (t["decision"] or {}).get("opciones"):
            sys.stderr.write('gresso: aviso: la decisión "%s" no trae opciones\n' % t.get("texto", ""))
        avisar_decision(tid, t.get("decision"))
        # Quien lee es "tu"; sin este campo, la tarea es del agente, como siempre.
        if str(t.get("quien", "")).strip().lower() in ("tu", "tú"):
            t["quien"] = "tu"
        if "ya" in t:
            urgente = es_si(t.pop("ya"))
            if urgente and de_la_persona(t):
                t["ya"] = True
            elif urgente:
                sys.stderr.write('gresso: aviso: %s es del agente y "ya" solo vale en lo que le toca a quien '
                                 'lee ("quien": "tu"); se lo quito\n' % tid)
    return fases


ICONOS = ("si", "no", "ya", "esperar", "pregunta", "gente", "dinero", "texto", "igual", "estrella",
          "lapiz", "flecha", "escudo")


def avisar_decision(tid, decision):
    """Lo que hace una decisión difícil de contestar, dicho al crearla y no cuando ya la está leyendo."""
    if not isinstance(decision, dict):
        return
    opciones = [o for o in decision.get("opciones") or [] if isinstance(o, dict)]
    recomendadas = [o for o in opciones if o.get("recomendada")]
    if len(recomendadas) > 1:
        sys.stderr.write("gresso: aviso: %s recomienda %d opciones; se recomienda una, o ninguna\n"
                         % (tid, len(recomendadas)))
    for o in recomendadas:
        if not o.get("porque"):
            sys.stderr.write('gresso: aviso: %s recomienda "%s" sin decir por qué ("porque")\n'
                             % (tid, o.get("texto", "")))
    if len(opciones) > 6:
        sys.stderr.write("gresso: aviso: %s tiene %d opciones; con más de seis cuesta comparar, y no caben en "
                         "las herramientas que preguntan desde el móvil\n" % (tid, len(opciones)))
    for o in opciones:
        if o.get("icono") and o["icono"] not in ICONOS:
            sys.stderr.write('gresso: aviso: %s usa el icono "%s", que no existe (hay: %s)\n'
                             % (tid, o["icono"], ", ".join(ICONOS)))


def es_si(valor):
    return str(valor).strip().lower() in ("1", "true", "si", "sí", "yes")


def de_la_persona(tarea):
    # Igual que en la página: lo suyo es lo que lleva "quien":"tu" y toda decisión.
    return tarea.get("quien") == "tu" or bool(tarea.get("decision"))


def avisar_ya(datos):
    urgentes = [t for f in datos.get("fases", []) for t in f.get("tareas", [])
                if t.get("ya") is True and t.get("estado") not in ("hecho", "descartado")]
    if len(urgentes) > MAX_YA:
        sys.stderr.write("gresso: aviso: hay %d tareas «ya» sin hacer, y con más de %d a la vez ninguna parece "
                         "urgente (las primeras: %s). Si alguna puede esperar, bájala con estado <ruta> tN=noya\n"
                         % (len(urgentes), MAX_YA, ", ".join(t.get("id", "?") for t in urgentes[:MAX_YA])))


# Algo que parece una contraseña a la vista. Se avisa sin repetirla, ni en la terminal.
PALABRA_SECRETA = re.compile(
    r"(contrase[nñ]a|password|passwd|pwd|clave|token|secret\w*|api[ _-]?key)"
    r"(?:\s+(?:es|era))?\s*[:=]?\s*[\"'«]?([^\s\"'»,;]{6,})",
    re.IGNORECASE,
)
FORMATO_SECRETO = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,})\b"
)


def parece_secreto(texto):
    if not isinstance(texto, str):
        return False
    if FORMATO_SECRETO.search(texto):
        return True
    for m in PALABRA_SECRETA.finditer(texto):
        # "la clave de API" o "la contraseña nueva" no enseñan nada: un valor lleva cifras o signos.
        if re.search(r"[\d@#$%&*!?_+=/-]", m.group(2)):
            return True
    return False


def textos_a_la_vista(datos):
    """Todo lo que la página enseña. Lo de "copiar" no se enseña, y por eso se queda fuera."""
    for campo in ("titulo", "subtitulo", "parte"):
        yield "el campo " + campo, datos.get(campo)
    for fase in datos.get("fases", []):
        for t in fase.get("tareas", []):
            nombre = "la tarea %s" % t.get("id", "?")
            for campo in ("texto", "nota", "porque", "dime"):
                yield nombre, t.get(campo)
            for paso in t.get("pasos") or []:
                yield nombre, paso
            for accion in t.get("acciones") or []:
                yield nombre, accion.get("texto")
            decision = t.get("decision") or {}
            yield nombre, decision.get("siNoDices")
            for opcion in decision.get("opciones") or []:
                for campo in ("texto", "detalle", "porque", "malo", "bueno", "cuesta", "noHace"):
                    yield nombre, opcion.get(campo)


def avisar_secretos(datos):
    avisados = set()
    for donde, texto in textos_a_la_vista(datos):
        if donde not in avisados and parece_secreto(texto):
            avisados.add(donde)
            sys.stderr.write('gresso: aviso: %s parece enseñar una contraseña o una clave. Quítala de '
                             'la vista y ponla en un botón: {"texto":"Copiar la contraseña","copiar":"..."}\n'
                             % donde)


def incrustar(html, datos, tocar=True):
    # Cambiar de plantilla (renovar) no es una novedad: la hora sigue siendo la del último cambio de
    # verdad, o la página diría «hoy» de un encargo parado desde hace días.
    if tocar or not datos.get("actualizado"):
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


def escribir(ruta, texto):
    # De una vez: la pestaña abierta nunca recarga un archivo a medio escribir.
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        f.write(texto)
    for _ in range(20):
        try:
            os.replace(temporal, ruta)
            return
        except PermissionError:
            # En Windows falla si el navegador está leyendo justo en ese momento.
            time.sleep(0.05)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    os.remove(temporal)


def guardar(ruta, html, datos, tocar=True):
    avisar_secretos(datos)
    avisar_ya(datos)
    escribir(ruta, incrustar(html, datos, tocar))
    # La página pide este script cada pocos segundos y solo recarga si ha cambiado. Va después
    # del HTML: si fuera antes, la pestaña podría recargar y seguir viendo lo de antes.
    escribir(ruta + ".version.js", 'window.__gressoVersion="%f";\n' % time.time())
    print(os.path.abspath(ruta))


def cuentas(datos):
    todas = [t for f in datos.get("fases", []) for t in f.get("tareas", [])]
    utiles = [t for t in todas if t.get("estado") != "descartado"]
    hechas = [t for t in utiles if t.get("estado") == "hecho"]
    # El porcentaje va por peso, igual que lo calcula la página: si no, la terminal y el
    # navegador dan cifras distintas para el mismo seguimiento.
    total = sum(peso(t) for t in utiles)
    hecho = sum(peso(t) for t in hechas)
    # Se redondea igual que la página (round de Python deja 12,5 en 12 y la página en 13).
    pct = int(hecho * 100.0 / total + 0.5) if total else 0
    # Mientras quede algo, nunca dice 100: redondear hacia arriba sería mentir.
    if pct > 99 and len(hechas) < len(utiles):
        pct = 99
    return todas, utiles, hechas, pct


def peso(tarea):
    p = tarea.get("peso")
    return p if isinstance(p, (int, float)) and not isinstance(p, bool) and p > 0 else 1


# ------------------------------------------------------- una sola página por frente
def archivo_registro():
    # Lo que se apunta: la ruta de cada seguimiento creado y su proyecto. Nada más.
    return os.environ.get("GRESSO_REGISTRO") or os.path.join(
        os.path.expanduser("~"), ".gresso", "seguimientos.json")


def leer_registro():
    try:
        with open(archivo_registro(), encoding="utf-8") as f:
            registro = json.load(f)
        return registro if isinstance(registro, dict) else {}
    except (OSError, ValueError):
        return {}


def apuntar_registro(ruta, proyecto):
    # Un fallo aquí nunca puede tumbar la orden: el seguimiento importa más que el aviso.
    if not proyecto:
        return
    try:
        registro = {r: p for r, p in leer_registro().items() if os.path.exists(r)}
        registro[os.path.abspath(ruta)] = proyecto
        destino = archivo_registro()
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(registro, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def proyecto_actual(explicito):
    """El proyecto es el que digan, o el repositorio de git donde se está trabajando."""
    if explicito:
        return str(explicito).strip()
    carpeta = os.getcwd()
    while True:
        if os.path.exists(os.path.join(carpeta, ".git")):
            return os.path.normcase(carpeta)
        arriba = os.path.dirname(carpeta)
        if arriba == carpeta:
            return None
        carpeta = arriba


def leer_seguimiento(ruta):
    """Los datos de un seguimiento, o None si ese archivo no es uno."""
    try:
        with open(ruta, encoding="utf-8") as f:
            m = MARCA.search(f.read())
        return json.loads(m.group(2).replace("<\\/", "</")) if m else None
    except (OSError, ValueError):
        return None


def otros_seguimientos(ruta, proyecto):
    """Los seguimientos sin terminar que hay en esa carpeta o para ese proyecto."""
    propia = os.path.normcase(os.path.abspath(ruta))
    carpeta = os.path.dirname(os.path.abspath(ruta))
    candidatas = []
    try:
        candidatas = [os.path.join(carpeta, n) for n in sorted(os.listdir(carpeta))
                      if n.lower().endswith((".html", ".htm"))]
    except OSError:
        pass
    if proyecto:
        candidatas += [r for r, p in sorted(leer_registro().items()) if p == proyecto]
    vistas, salida = {propia}, []
    for candidata in candidatas:
        clave = os.path.normcase(os.path.abspath(candidata))
        if clave in vistas:
            continue
        vistas.add(clave)
        datos = leer_seguimiento(candidata)
        if datos is None:
            continue
        _, utiles, hechas, pct = cuentas(datos)
        if utiles and len(hechas) == len(utiles):
            continue
        salida.append((candidata, datos.get("titulo", "Seguimiento"), pct, datos.get("actualizado", "?")))
    return salida


def avisar_otros(ruta, proyecto):
    otros = otros_seguimientos(ruta, proyecto)
    if not otros:
        return
    sys.stderr.write("gresso: aviso: ya hay otro seguimiento abierto. Una persona no debería "
                     "preguntarse cuál es el bueno: si es el mismo frente, añade ahí con anadir.\n")
    for otra, titulo, pct, actualizado in otros:
        sys.stderr.write("  %s (%d %%, actualizado %s): %s\n" % (titulo, pct, actualizado, otra))


def copia_si_existe(ruta):
    # Reescribir un seguimiento que ya existe no puede costar lo que tenía dentro.
    if leer_seguimiento(ruta) is None:
        return
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    with open(ruta + ".bak", "w", encoding="utf-8") as f:
        f.write(contenido)
    sys.stderr.write("gresso: aviso: %s ya existía; lo anterior queda en %s.bak\n" % (ruta, ruta))


# --------------------------------------------------------------------------- marca
def imagen_en_linea(valor, carpeta):
    """Convierte un archivo o un <svg> en data:, para que la página siga siendo un solo archivo."""
    valor = str(valor).strip()
    if valor.startswith("data:image/"):
        return valor
    if valor.startswith("<"):
        crudo, tipo = valor.encode("utf-8"), "image/svg+xml"
    else:
        ruta = valor if os.path.isabs(valor) else os.path.join(carpeta, valor)
        if not os.path.exists(ruta):
            muere("la marca apunta a una imagen que no existe: %s" % ruta)
        with open(ruta, "rb") as f:
            crudo = f.read()
        tipo = mimetypes.guess_type(ruta)[0]
        if not tipo or not tipo.startswith("image/"):
            muere("eso no parece una imagen: %s" % ruta)
    return "data:%s;base64,%s" % (tipo, base64.b64encode(crudo).decode("ascii"))


def preparar_marca(marca, carpeta):
    if not isinstance(marca, dict):
        muere("la marca tiene que ser un objeto JSON")
    for campo in ("logo", "logoOscuro", "mascota", "mascotaOscura"):
        if marca.get(campo):
            marca[campo] = imagen_en_linea(marca[campo], carpeta)
    return marca


def leer_marca(archivo):
    return preparar_marca(leer_entrada(archivo), os.path.dirname(os.path.abspath(archivo)))


def cargar_plantilla(origen, titulo):
    origen = origen or plantilla_por_defecto()
    if not os.path.exists(origen):
        muere("no encuentro la plantilla en %s" % origen)
    with open(origen, encoding="utf-8") as f:
        return f.read().replace("__TITULO__", escape_html.escape(titulo))


# --------------------------------------------------------------------------- crear
def cmd_crear(ruta, resto):
    titulo = subtitulo = plantilla = archivo = proyecto = marca = None
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
        elif resto[i] == "--proyecto" and i + 1 < len(resto):
            proyecto = resto[i + 1]; i += 2
        elif resto[i] == "--marca" and i + 1 < len(resto):
            marca = resto[i + 1]; i += 2
        else:
            i += 1

    datos = leer_entrada(archivo)
    if titulo:
        datos["titulo"] = titulo
    if subtitulo:
        datos["subtitulo"] = subtitulo
    datos.setdefault("titulo", "Seguimiento")
    datos["fases"] = numerar(datos.get("fases", []))

    if marca:
        datos["marca"] = leer_marca(marca)
    elif datos.get("marca"):
        datos["marca"] = preparar_marca(datos["marca"], os.getcwd())
    html = cargar_plantilla(plantilla, datos["titulo"])

    carpeta = os.path.dirname(os.path.abspath(ruta))
    if carpeta and not os.path.isdir(carpeta):
        os.makedirs(carpeta)
    proyecto = proyecto_actual(proyecto or datos.get("proyecto"))
    avisar_otros(ruta, proyecto)
    copia_si_existe(ruta)
    guardar(ruta, html, datos)
    apuntar_registro(ruta, proyecto)


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
            quien = ("tú, ya: " if t.get("ya") is True else "tú: ") if de_la_persona(t) else ""
            print("  %-6s %-11s %s%s%s" % (t.get("id", "?"), t.get("estado", "pendiente"),
                                           quien, t.get("texto", ""), nota))


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
        if valor == "ya":
            # No cambia el estado: la sube arriba, a lo que tiene que hacer ya.
            if not de_la_persona(indice[tid]):
                muere('%s es del agente: "ya" solo vale en lo que le toca a quien lee ("quien": "tu")' % tid)
            indice[tid]["ya"] = True
        elif valor == "noya":
            indice[tid].pop("ya", None)
        elif valor not in ESTADOS:
            muere('"%s" no es un estado; los válidos son: %s (y ya o noya, para subir o bajar lo urgente '
                  'de quien lee)' % (valor, ", ".join(ESTADOS)))
        else:
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


# ---------------------------------------------------------------------- decisiones
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def orden_decisiones(datos):
    """Las decisiones abiertas en el orden de la página, que es el de sus letras: primero las de
    arriba («ya»), y luego las de abajo, con las urgentes que no cupieron arriba delante."""
    todas = [t for f in datos.get("fases", []) for t in f.get("tareas", [])]

    def abierta(t):
        return t.get("estado") not in ("hecho", "descartado")

    def urgente(t):
        return t.get("ya") is True and (t.get("quien") == "tu" or isinstance(t.get("decision"), dict))

    arriba = [t for t in todas if urgente(t) and abierta(t)][:MAX_YA]
    abajo = [t for t in todas if isinstance(t.get("decision"), dict) and abierta(t)
             and not any(t is a for a in arriba)]
    abajo = [t for t in abajo if urgente(t)] + [t for t in abajo if not urgente(t)]
    return [t for t in arriba if isinstance(t.get("decision"), dict)] + abajo


def plano(texto):
    return escape_html.unescape(re.sub(r"<[^>]+>", "", str(texto or ""))).strip()


def cmd_decisiones(ruta):
    """Las mismas preguntas que enseña la página, para hacerlas también por otro sitio (el móvil):
    con su letra, en el mismo orden y con las opciones numeradas igual, para que «A uno» sea lo mismo."""
    _, datos = extraer(ruta)
    salida = []
    for i, t in enumerate(orden_decisiones(datos)):
        decision = t["decision"]
        contexto = " ".join(x for x in (plano(t.get("porque")), plano(decision.get("siNoDices"))) if x)
        pregunta = {"letra": LETRAS[i] if i < len(LETRAS) else str(i + 1), "id": t.get("id"),
                    "title": t.get("texto", "")}
        if contexto:
            pregunta["context"] = contexto
        opciones = []
        for o in decision.get("opciones") or []:
            o = o if isinstance(o, dict) else {"texto": str(o)}
            opcion = {"text": o.get("texto", "")}
            if o.get("detalle"):
                opcion["detail"] = plano(o["detalle"])
            if o.get("recomendada"):
                opcion["recommended"] = True
            opciones.append(opcion)
        pregunta["options"] = opciones
        salida.append(pregunta)
    print(json.dumps(salida, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------------- renovar
def cmd_renovar(ruta, resto):
    plantilla = marca = None
    i = 0
    while i < len(resto):
        if resto[i] == "--marca" and i + 1 < len(resto):
            marca = resto[i + 1]; i += 2
        elif resto[i] == "--plantilla" and i + 1 < len(resto):
            plantilla = resto[i + 1]; i += 2
        else:
            i += 1
    _, datos = extraer(ruta)
    if marca:
        datos["marca"] = leer_marca(marca)
    html = cargar_plantilla(plantilla, datos.get("titulo", "Seguimiento"))
    copia_si_existe(ruta)
    guardar(ruta, html, datos, tocar=False)


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
    elif orden == "renovar":
        cmd_renovar(ruta, resto)
    elif orden == "decisiones":
        cmd_decisiones(ruta)
    else:
        muere('orden desconocida "%s" (crear, ver, estado, parte, anadir, renovar, decisiones)' % orden)


if __name__ == "__main__":
    main()
