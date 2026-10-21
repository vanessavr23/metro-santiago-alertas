---
name: metro-santiago-alertas
description: Consulta el estado de la red de Metro de Santiago (líneas y estaciones) y opera, diagnostica o despliega el monitor de alertas por Telegram/Discord de este repo. Úsala cuando pregunten si hay estaciones cerradas, por el estado del Metro, o al modificar o reparar el monitor.
---

# Metro Santiago · estado de la red y alertas

El monitor de este repo es un script determinista (`check_metro.py`, solo librería
estándar de Python 3.10+) que GitHub Actions ejecuta cada 10 minutos. No usa LLM al
ejecutarse: esta Skill sirve para consultarlo, mantenerlo y diagnosticarlo.

## Fuente de datos

- Endpoint: `https://www.metro.cl/api/estadoRedDetalle.php` (JSON, sin autenticación).
- Formato: `{ "l1": { "estado", "mensaje", "mensaje_app", "estaciones": [ { "nombre",
  "codigo", "estado", "combinacion", "descripcion", "descripcion_app", "mensaje" } ] }, ... }`
- Líneas: `l1`, `l2`, `l3`, `l4`, `l4a`, `l5`, `l6` (`l7` cuando se inaugure).
- `estado == "1"` es normal. Hay otros códigos (2 a 4) sin documentación oficial: el
  script trata cualquier otro valor como incidencia y usa los textos del JSON.
  Los significados observados se van guardando en `estado.json` → `codigos_vistos`.
- Resumen solo por línea: `/api/estadoRed.php`. Horarios: `/api/horariosEstacion.php?cod=<codigo>`.

## Tareas

### "¿Hay estaciones cerradas?" / "¿Cómo está el Metro?"
1. Ejecuta `python check_metro.py --consultar` (no alerta ni modifica archivos).
2. Si el entorno no tiene salida a metro.cl, lee `estado.json` del repo (último estado
   guardado por la Action) e indica la hora de `ultimo_cambio`.
3. Responde con las líneas/estaciones distintas de normal; si todo está normal, dilo en una línea.

### Probar los canales de alerta
`python check_metro.py --probar-envio` con `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` y/o
`DISCORD_WEBHOOK_URL` definidos. En GitHub: Actions → "Monitoreo Metro Santiago" →
Run workflow → marcar "Enviar un mensaje de prueba".

### Diagnosticar una Action en rojo
- `No se pudo consultar ...` tres veces seguidas → metro.cl caído, bloqueando IPs de
  GitHub o el endpoint cambió. Abre la página https://www.metro.cl/el-viaje/estado-red,
  revisa las peticiones de red y actualiza `METRO_API_URL` / `normalizar()`.
- `formato inesperado` → cambió el JSON: ajusta `normalizar()` y la fixture de `tests/`.
- `Error al enviar la alerta: HTTP 401/400` → token o chat_id incorrectos (secrets).
- Workflow desactivado → GitHub lo apaga tras 60 días sin actividad; `keepalive.yml` lo
  evita. Reactívalo desde la pestaña Actions si ocurre.

### Modificar el monitor
1. Cambia `check_metro.py` manteniendo cero dependencias externas.
2. Agrega o ajusta pruebas en `tests/` y ejecuta `python -m unittest discover -s tests`.
3. Reglas que no se deben romper: alertar solo cuando cambia el estado (sin spam),
   no guardar estado si el envío falla (para reintentar), escapar HTML en mensajes de
   Telegram, y no exponer tokens en logs ni en el código.

## Despliegue desde cero (costo $0)
1. Repo público en GitHub (minutos de Actions ilimitados) con estos archivos.
2. Bot de Telegram con @BotFather → token; enviar un mensaje al bot y obtener el
   `chat_id` en `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Secrets del repo: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (y opcional `DISCORD_WEBHOOK_URL`).
4. Ejecutar el workflow manualmente con "mensaje de prueba" para verificar todo.
