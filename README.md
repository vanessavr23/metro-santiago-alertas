# Alertas Metro de Santiago 🚇

Avisa por **Telegram** (o Discord) cuando una estación o línea del Metro de Santiago
cambia de estado: cierres, accesos restringidos y reaperturas. Corre gratis en
GitHub Actions cada 10 minutos y no usa IA al ejecutarse.

- Fuente: `https://www.metro.cl/api/estadoRedDetalle.php`, el mismo JSON que usa metro.cl.
- Solo alerta **cuando algo cambia**. Si una estación pasa 3 horas cerrada, llegan
  dos mensajes: el cierre y la reapertura.
- Sin dependencias: solo Python 3.10+ estándar.

## Puesta en marcha

1. **Crear el bot**: en Telegram, habla con [@BotFather](https://t.me/BotFather),
   envía `/newbot` y guarda el token.
2. **Obtener tu chat_id**: envía cualquier mensaje a tu bot y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates`. El número en
   `"chat":{"id": ...}` es tu chat_id. Para un grupo, agrega el bot al grupo; su id
   empieza con `-`.
3. **Guardar los secretos**: en el repo, ve a *Settings → Secrets and variables →
   Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DISCORD_WEBHOOK_URL` (opcional)
4. **Probar**: ve a *Actions → Monitoreo Metro Santiago → Run workflow*, marca
   "Enviar un mensaje de prueba" y ejecútalo. Debería llegarte un mensaje, y el
   primer `estado.json` quedará guardado en el repo.

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
| `estado.json` | Último estado conocido. Lo actualiza la Action cuando hay cambios |
| `.github/workflows/metro_check.yml` | Ejecución cada 10 min y ejecución manual |
| `.github/workflows/keepalive.yml` | Latido mensual: evita que GitHub apague el cron tras 60 días |
| `.github/workflows/tests.yml` | Pruebas en cada cambio de código |
| `.claude/skills/metro-santiago-alertas/` | Skill para consultar, diagnosticar y mantener el monitor con Claude Code |

## Notas

- **Costo $0**: el repo debe ser **público**. En repos privados, ejecutar cada
  10 minutos supera los 2.000 minutos gratis al mes. Los secretos siguen protegidos
  aunque el repo sea público.
- **Retrasos**: GitHub puede atrasar varios minutos las ejecuciones programadas.
- **Fallas de consulta**: si metro.cl no responde 3 veces seguidas, llega un aviso y
  la ejecución queda en rojo una vez. GitHub además avisa por correo. Cuando la
  consulta se recupera, también llega un aviso.
- **Códigos de estado**: `"1"` es normal. Los otros (2–4) no tienen documentación
  oficial. El script usa los textos que trae el JSON y va registrando lo que observa
  en `estado.json → codigos_vistos`.
