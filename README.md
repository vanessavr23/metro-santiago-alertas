# Alertas Metro de Santiago 🚇

Avisa por **Telegram** (o Discord) cuando una estación o línea del Metro de Santiago
cambia de estado: cierres, accesos restringidos y reaperturas. Revisa cada 10 minutos
desde **tu PC con Windows** y no usa IA al ejecutarse.

- Fuente: `https://www.metro.cl/api/estadoRedDetalle.php`, el mismo JSON que usa metro.cl.
- Solo alerta **cuando algo cambia**. Si una estación pasa 3 horas cerrada, llegan
  dos mensajes: el cierre y la reapertura.
- Sin dependencias: solo Python 3.10+ estándar.

> **¿Por qué no en GitHub Actions?** metro.cl bloquea las IPs de centros de datos
> extranjeros: desde los servidores de GitHub (EE. UU.) responde `403 Acceso
> restringido`. Por eso el monitor corre desde una conexión chilena, como tu PC.
> El workflow quedó solo para ejecución manual.

## Instalación en Windows

1. **Crear el bot**: en Telegram, habla con [@BotFather](https://t.me/BotFather),
   envía `/newbot` y copia el token.
2. **Descargar el repo y ejecutar el instalador** en PowerShell:
   ```powershell
   cd $HOME
   git clone https://github.com/vanessavr23/metro-santiago-alertas
   cd metro-santiago-alertas
   powershell -ExecutionPolicy Bypass -File .\instalar_windows.ps1
   ```
   Si no tienes git, usa *Code → Download ZIP* en GitHub, descomprime y haz
   **doble clic en `INSTALAR.bat`** (equivale a la última línea).
3. El instalador:
   - busca Python (y ofrece instalarlo si falta),
   - prueba la conexión a metro.cl,
   - te pide el token,
   - detecta tu `chat_id` cuando le escribes al bot,
   - envía un mensaje de prueba,
   - programa la tarea **"Metro Santiago Alertas"** cada 10 minutos, sin ventanas.

La configuración queda en `.env`, el último estado en `estado.json` y el registro en
`monitor.log`. Los tres están en `.gitignore`, así que nunca se suben a GitHub.

**Limitación**: solo alerta mientras tu sesión de Windows está abierta y el PC no está
suspendido. Al volver, la tarea se pone al día sola. Para tener alertas 24/7, sirven
el mismo script y la misma Skill en un celular Android viejo (Termux) o una Raspberry Pi.

**Detener / desinstalar**: doble clic en `DESINSTALAR.bat`. Elimina la tarea programada y conserva `.env`, `estado.json` y `monitor.log`. Para reactivarlo, vuelve a ejecutar `INSTALAR.bat` y responde **s** cuando pregunte si mantener la configuración.

**Pruebas de alertas**: si dejas un `simulacion.json` (mismo formato que el endpoint) junto al script, la siguiente revisión lo usa en lugar de metro.cl, marca el mensaje como 🧪 SIMULACIÓN y borra el archivo.

## Uso local

```bash
python check_metro.py --consultar      # estado actual, sin alertar
python check_metro.py --probar-envio   # prueba de Telegram/Discord
python check_metro.py                  # verificación normal (usa estado.json)
python -m unittest discover -s tests   # pruebas
```

## Archivos

| Archivo | Para qué |
|---|---|
| `check_metro.py` | Consulta, compara con `estado.json` y envía alertas |
| `instalar_windows.ps1` | Instalador y desinstalador de la tarea programada en Windows |
| `.env`, `estado.json`, `monitor.log` | Configuración, último estado y registro (locales, no se suben) |
| `.github/workflows/metro_check.yml` | Ejecución manual (el cron está apagado por el bloqueo de IP) |
| `.github/workflows/keepalive.yml` | Latido mensual, solo útil si algún día se reactiva el cron |
| `.github/workflows/tests.yml` | Pruebas en cada cambio de código |
| `.claude/skills/metro-santiago-alertas/` | Skill para consultar, diagnosticar y mantener el monitor con Claude Code |

## Notas

- **Fallas de consulta**: si metro.cl no responde 3 veces seguidas, llega un aviso
  por Telegram. Cuando la consulta se recupera, también llega un aviso.
- **VPN**: una VPN con salida fuera de Chile puede provocar el mismo bloqueo 403.
- **Códigos de estado**: `"1"` es normal. Los otros (2–4) no tienen documentación
  oficial. El script usa los textos que trae el JSON y va registrando lo que observa
  en `estado.json → codigos_vistos`.
