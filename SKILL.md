---
name: gresso
description: Monta el documento de seguimiento de un encargo largo como un HTML de un solo archivo que el agente va reescribiendo mientras trabaja, con barra de progreso, porcentaje, cuántas tareas quedan, cuáles están hechas, cuáles en curso y cuáles bloqueadas, en una ruta fija que se mira pulsando F5. Úsalo al empezar cualquier trabajo de varios pasos o que vaya a durar un rato, y cuando pidan "qué queda por hacer", "un seguimiento", "ponme el progreso", "una lista con casillas", "un HTML que se vaya actualizando", "quiero ver por dónde vas sin preguntarte" o "/gresso". Sustituye a ir cantando el avance por la terminal.
---

# Gresso

El progreso de un encargo en una página que no hay que pedir: lo hecho, lo que queda y lo que
está parado. Mientras el agente trabaja va reescribiendo el mismo archivo, así que cualquiera
abre la pestaña, pulsa `F5` y ve por dónde va **sin cortarle y sin esperar al cierre**.

Sin esto hay dos salidas malas: preguntarle al agente (y pararlo) o esperar al resumen final.
Un seguimiento que solo se escribe al terminar no es un seguimiento, es un informe.

## Cuándo se usa, y cuándo no

**Sí**, en cuanto el encargo tenga **cuatro pasos o más**, o vaya a durar más de unos minutos:
levantar algo nuevo, una migración, una auditoría, un plan con casillas, limpiar un repo
entero, el parte de lo que queda por desarrollar en un proyecto.

**No**, para una respuesta de una sola vez, un arreglo de dos líneas, ni una página donde hay
que elegir entre opciones. Montar un seguimiento para tres pasos es ceremonia, y una
herramienta que salta a cada rato se acaba ignorando entera.

## Proceso

Todo pasa por `scripts/gresso.py`, dentro de la carpeta de esta skill (la que aparece como
directorio base al cargarla). Python 3, sin dependencias. En los ejemplos, `GRESSO` es la ruta
a ese script; en Windows, `python` en vez de `python3`.

### 1. Parte el encargo en tareas antes de tocar nada

Cada tarea es **una cosa que se puede dar por cerrada de una vez**, dicha en una frase y en
palabras llanas: quien lo lee quiere saber qué falta, no leerse tu plan técnico. Si una tarea
necesita una lista de viñetas para contarse, son varias tareas.

Agrúpalas en **fases** cuando el trabajo tenga etapas de verdad (`Montaje`, `Pruebas`,
`Publicación`). Si no las tiene, una sola fase y ya; inventar fases para que la página parezca
más seria es ruido.

Cada tarea admite:

- `texto` - la frase. Obligatorio.
- `estado` - `pendiente` (por defecto), `haciendo`, `hecho`, `bloqueado`, `descartado`.
- `nota` - una línea de detalle, y en lo bloqueado **qué falta exactamente** para desbloquearlo.
- `peso` - un número, solo cuando una tarea vale por varias y un porcentaje plano mentiría.
- `id` - se lo pone el script solo (`t1`, `t2`...). Un id **no cambia nunca**, aunque luego se
  añadan tareas en medio, así que se puede recordar para marcarla después.

Lo `descartado` sale del total: no es trabajo que quede, y dejarlo contando hunde el porcentaje
sin motivo. Se queda escrito y tachado, porque saber qué se decidió no hacer es información.

### 2. Crea el archivo en una ruta que no cambie

En la carpeta temporal de la sesión si es el parte de un encargo, **nunca dentro del código del
proyecto**. El nombre no lleva fecha ni número de versión: la misma pestaña tiene que servir de
principio a fin.

```bash
python3 "$GRESSO" crear "<carpeta temporal>/seguimiento.html" <<'EOF'
{
  "titulo": "Migrar la web a Cloudflare",
  "subtitulo": "Lo que queda para que el dominio sirva con HTTPS y despliegue solo.",
  "parte": "Arrancando: todavía no he tocado el DNS.",
  "fases": [
    {"nombre": "Preparar", "tareas": [
      {"texto": "Crear el token de API con los permisos justos", "estado": "haciendo"},
      {"texto": "Conectar el repositorio a Pages"}
    ]},
    {"nombre": "Comprobar", "tareas": [
      {"texto": "Que el candado salga en el dominio y en www"}
    ]}
  ]
}
EOF
```

Si la tubería da guerra (o el JSON es largo), escríbelo en un archivo y pásalo con
`--datos archivo.json`, que vale igual en `crear` y en `anadir`. La entrada se lee en UTF-8, y si
no lo es en cp1252, así que las tildes y las eñes llegan bien también en Windows.

El script imprime la ruta absoluta y nada más. **No abras la plantilla ni el HTML generado con
las herramientas de leer archivo**: son cientos de líneas que no necesitas en el contexto, y
para eso está `ver`.

### 3. Ábrelo una vez, delante, y dilo en una línea

Ábrelo tú mismo en el navegador (`Start-Process "<ruta>"` en Windows, `open` en macOS,
`xdg-open` en Linux), sin pedir permiso y sin limitarte a dejar la ruta escrita para que otro la
abra a mano. En el chat, **una sola línea**: qué estás haciendo y que con `F5` lo ve al día.
Nunca repitas la lista de tareas en la terminal: ya la tiene delante.

La página **no se refresca sola**, y es a propósito: así no se le mueve mientras lee.

### 4. Reescríbelo cada vez que avanzas, no al final

Esta es la skill entera. Al cerrar un paso, al empezar el siguiente, al chocar con un bloqueo
y al cambiar el plan:

```bash
# cambiar estados (varios de una vez); con ":" detrás se pone la nota, y con ":" solo se borra
python3 "$GRESSO" estado "<ruta>" t1=hecho t2=haciendo "t5=bloqueado:falta la clave de API"

# el parte de situación de arriba, en dos o tres líneas
python3 "$GRESSO" parte "<ruta>" "DNS ya apuntando. Esperando a que propague para probar el candado."

# tareas que aparecen por el camino (lo normal, no un fallo del plan)
python3 "$GRESSO" anadir "<ruta>" --fase "Comprobar" <<'EOF'
[{"texto": "Redirigir www al dominio sin www"}]
EOF

# recordar qué ids hay, sin cargar el HTML en el contexto
python3 "$GRESSO" ver "<ruta>"
```

Cada uno de esos comandos reescribe también **la fecha y la hora de arriba**, que es lo único
que le dice al lector si lo que mira es de ahora.

Dos trampas que lo convierten en un informe sin que te des cuenta:

1. **Marcar varias tareas de golpe al terminar.** Si la página pasa de 20% a 100% en un solo
   salto, no ha servido para nada mientras trabajabas.
2. **No apuntar lo que surge.** Las tareas nuevas se añaden cuando aparecen; un porcentaje que
   solo sube porque el plan se hizo pequeño es mentira.

### 5. Al cerrar

Deja todo en su estado real, incluido lo que quedó sin hacer y por qué. Un seguimiento que
termina con tareas en `haciendo` para siempre es basura. Si el encargo sigue mañana, **el
archivo se queda**: es el único sitio donde está lo que faltaba.

Si lo que seguías es del proyecto y no de la sesión (lo que queda por desarrollar), la fuente
sigue siendo la del proyecto (su lista de metas, su `TODO.md` o lo que use): **el HTML es su
vista, se regenera cuando cambia la fuente y nunca manda sobre ella.** Y si es un documento
interno, no se sube a un repositorio público.

## Lo que ya trae la plantilla, y no hay que tocar

- **Un solo archivo, cero CDN.** Tiene que verse igual sin internet.
- **Tema del sistema sin botón**, claro u oscuro por `prefers-color-scheme`, y legible en el
  móvil (la barra deja de ir pegada arriba en pantallas estrechas para no taparlo todo).
- **Barra de progreso en tres tramos**: hecho en verde, en curso en azul, bloqueado en rojo.
  De un vistazo se ve si lo que falta está parado o en marcha.
- **Porcentaje grande, y las tareas que quedan en número**, que es la pregunta de verdad.
- **Los bloqueos suben arriba del todo**, en su propia caja, antes que ninguna tarea.
- **Mini barra por fase**, con su propio `hechas/total` y su porcentaje.
- **La hora de la última actualización en la cabecera**, y el porcentaje también en el título de
  la pestaña, para verlo sin cambiar de ventana.
- **Recargar no te mueve de sitio**: guarda el scroll antes de salir y vuelve donde estabas.

Si el proyecto donde trabajas tiene su propio sistema de diseño, cambia los valores del bloque
`PALETA` de la plantilla (los `--bg`, `--acento`, `--radio`, la tipografía) con un `replace` de
una pasada. El bloque `ESTRUCTURA` de debajo **no se toca nunca**: todo va por `var()`, así que
hereda el cambio de piel solo.

## Archivos

- `references/plantilla.html` - la página. Se copia, no se edita a mano.
- `scripts/gresso.py` - crea y actualiza el bloque de datos sin que el HTML pase por el modelo.
