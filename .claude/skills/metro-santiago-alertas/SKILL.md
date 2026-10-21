---
name: metro-santiago-alertas
description: Consulta el estado de la red de Metro de Santiago (líneas y estaciones) y opera, diagnostica o despliega el monitor de alertas por Telegram/Discord de este repo. Úsala cuando pregunten si hay estaciones cerradas, por el estado del Metro, o al modificar o reparar el monitor.
---

# Metro Santiago · estado de la red y alertas

El monitor de este repo es un script determinista (`check_metro.py`, solo librería
estándar de Python 3.10+). Una tarea programada de Windows ("Metro Santiago Alertas",
creada por `instalar_windows.ps1`) lo ejecuta cada 10 minutos en el PC de la usuaria.
No usa LLM al ejecutarse: esta Skill sirve para consultarlo, mantenerlo y diagnosticarlo.

**Restricción clave**: metro.cl bloquea IPs de centros de datos extranjeros. GitHub
Actions recibe `403 Acceso restringido`. Solo funciona desde conexiones chilenas,
como el PC de casa, un celular con Termux o una Raspberry Pi. No intentes evadir el
bloqueo con proxies.

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
2. Si falla con 403 o sin conexión (por ejemplo, en un sandbox en la nube), lee el
   `estado.json` local, que es el último estado guardado por la tarea, e indica la hora
   de `ultimo_cambio`.
3. Responde con las líneas/estaciones distintas de normal; si todo está normal, dilo en una línea.

### Probar los canales de alerta
`python check_metro.py --probar-envio` con `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` y/o
`DISCORD_WEBHOOK_URL` definidos. La configuración local está en `.env` (no se sube a git).

### Diagnosticar fallas
- Revisa `monitor.log` y la tarea con `Get-ScheduledTask "Metro Santiago Alertas" | Get-ScheduledTaskInfo`
  (LastTaskResult 0 = bien).
- `HTTP Error 403` → bloqueo de IP: ¿VPN activa o se está ejecutando fuera de Chile?
- `No se pudo consultar ...` tres veces seguidas → metro.cl caído o el endpoint cambió. Abre la página https://www.metro.cl/el-viaje/estado-red,
  revisa las peticiones de red y actualiza `METRO_API_URL` / `normalizar()`.
- `formato inesperado` → cambió el JSON: ajusta `normalizar()` y la fixture de `tests/`.
- `Error al enviar la alerta: HTTP 401/400` → token o chat_id incorrectos en `.env`.
- No llegan alertas → ¿PC suspendido o sesión cerrada? La tarea solo corre con la sesión abierta.

### Modificar el monitor
1. Cambia `check_metro.py` manteniendo cero dependencias externas.
2. Agrega o ajusta pruebas en `tests/` y ejecuta `python -m unittest discover -s tests`.
3. Reglas que no se deben romper: alertar solo cuando cambia el estado (sin spam),
   no guardar estado si el envío falla (para reintentar), escapar HTML en mensajes de
   Telegram, y no exponer tokens en logs ni en el código.

## Despliegue desde cero (costo $0)
1. Clonar el repo en un equipo con conexión chilena.
2. Windows: `powershell -ExecutionPolicy Bypass -File .\instalar_windows.ps1`. Configura
   el bot, el `chat_id`, el mensaje de prueba y la tarea cada 10 min.
   Para desinstalar, agrega `-Desinstalar`.
3. Linux, Termux o Raspberry Pi: crear `.env` con `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`,
   y agregar a crontab: `*/10 * * * * cd /ruta/repo && python3 check_metro.py --log monitor.log`.
