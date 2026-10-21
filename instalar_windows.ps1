<#
  Instalador del monitor de Metro de Santiago en Windows.

  Uso (desde la carpeta del repo, en PowerShell):
      powershell -ExecutionPolicy Bypass -File .\instalar_windows.ps1
      powershell -ExecutionPolicy Bypass -File .\instalar_windows.ps1 -Desinstalar

  Qué hace:
    1. Busca Python 3.10+ (ofrece instalarlo con winget si falta).
    2. Verifica que este PC pueda consultar metro.cl.
    3. Configura el bot de Telegram en un archivo .env local (no se sube a GitHub).
    4. Envía un mensaje de prueba y guarda el estado inicial.
    5. Programa una tarea de Windows que revisa cada 10 minutos, sin abrir ventanas.
#>
param(
    [int]$Minutos = 10,
    [switch]$Desinstalar
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$env:PYTHONIOENCODING = 'utf-8'
$NombreTarea = 'Metro Santiago Alertas'
$Carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Carpeta 'check_metro.py'
$EnvFile = Join-Path $Carpeta '.env'
$LogFile = Join-Path $Carpeta 'monitor.log'

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Ok($texto)   { Write-Host "   OK  $texto" -ForegroundColor Green }
function Aviso($texto){ Write-Host "   !!  $texto" -ForegroundColor Yellow }

if ($Desinstalar) {
    if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
        Ok "Tarea '$NombreTarea' eliminada. Los archivos .env, estado.json y monitor.log siguen en $Carpeta."
    } else {
        Aviso "No existe la tarea '$NombreTarea'."
    }
    exit 0
}

if (-not (Test-Path $Script)) { throw "No encuentro check_metro.py en $Carpeta" }

# --------------------------------------------------------------------------- 1
Paso 'Buscando Python 3.10 o superior'
function Buscar-Python {
    $candidatos = @(
        @('py', '-3'),
        @('python'),
        @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"),
        @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
    )
    foreach ($c in $candidatos) {
        try {
            $argsPy = @($c | Select-Object -Skip 1) + @('-c', 'import sys; print(sys.executable); print(sys.version_info >= (3, 10))')
            $salida = & $c[0] @argsPy 2>$null
            if ($LASTEXITCODE -eq 0 -and $salida.Count -ge 2 -and $salida[1].Trim() -eq 'True' -and
                $salida[0] -notmatch 'WindowsApps') {
                return $salida[0].Trim()
            }
        } catch { }
    }
    return $null
}
$Python = Buscar-Python
if (-not $Python) {
    Aviso 'No encontré Python 3.10+.'
    $r = Read-Host '   ¿Instalar Python 3.12 para tu usuario con winget? (s/n)'
    if ($r -notmatch '^[sS]') { throw 'Instala Python desde https://www.python.org/downloads/ y vuelve a ejecutar este instalador.' }
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $Python = Buscar-Python
    if (-not $Python) { throw 'Python se instaló pero no lo encuentro. Cierra y abre PowerShell y vuelve a ejecutar el instalador.' }
}
$PythonW = Join-Path (Split-Path $Python) 'pythonw.exe'
if (-not (Test-Path $PythonW)) { $PythonW = $Python }
Ok "Python: $Python"

# --------------------------------------------------------------------------- 2
Paso 'Probando la conexión con metro.cl desde este PC'
& $Python $Script --consultar
if ($LASTEXITCODE -ne 0) {
    Aviso 'No se pudo consultar metro.cl. Revisa tu conexión (una VPN fuera de Chile puede causar bloqueo).'
    $r = Read-Host '   ¿Continuar de todos modos? (s/n)'
    if ($r -notmatch '^[sS]') { exit 1 }
} else { Ok 'metro.cl responde' }

# --------------------------------------------------------------------------- 3
Paso 'Configurando Telegram'
$configurar = $true
if (Test-Path $EnvFile) {
    $r = Read-Host '   Ya existe una configuración (.env). ¿Mantenerla? (s/n)'
    if ($r -match '^[sS]') { $configurar = $false; Ok 'Se mantiene la configuración actual' }
}
if ($configurar) {
    Write-Host '   Si aún no tienes bot: en Telegram abre @BotFather, envía /newbot y copia el token.'
    $seguro = Read-Host '   Pega el token del bot (no se mostrará)' -AsSecureString
    $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)).Trim()
    if ($Token -notmatch '^\d+:[\w-]{30,}$') { throw 'El token no tiene el formato esperado (números:letras).' }

    try { $bot = Invoke-RestMethod "https://api.telegram.org/bot$Token/getMe" }
    catch { throw 'Telegram rechazó el token. Revísalo en @BotFather.' }
    Ok "Bot válido: @$($bot.result.username)"

    Write-Host "   Ahora envía cualquier mensaje a @$($bot.result.username) en Telegram"
    Write-Host '   (o agrégalo a un grupo y escribe algo ahí) y presiona Enter.'
    $ChatId = $null
    for ($i = 0; $i -lt 3 -and -not $ChatId; $i++) {
        Read-Host '   [Enter cuando hayas enviado el mensaje]' | Out-Null
        $upd = Invoke-RestMethod "https://api.telegram.org/bot$Token/getUpdates"
        $chats = @($upd.result | ForEach-Object {
            if ($_.message) { $_.message.chat } elseif ($_.my_chat_member) { $_.my_chat_member.chat }
        } | Where-Object { $_ } | Sort-Object id -Unique)
        if ($chats.Count -eq 1) { $ChatId = $chats[0].id }
        elseif ($chats.Count -gt 1) {
            for ($j = 0; $j -lt $chats.Count; $j++) {
                $nombre = if ($chats[$j].title) { $chats[$j].title } else { "$($chats[$j].first_name) (privado)" }
                Write-Host "     [$j] $nombre  id=$($chats[$j].id)"
            }
            $ChatId = $chats[[int](Read-Host '   ¿A cuál chat envío las alertas? Número')].id
        } else { Aviso 'Todavía no veo mensajes. Envía uno al bot e inténtalo otra vez.' }
    }
    if (-not $ChatId) { $ChatId = Read-Host '   Escribe el chat_id manualmente' }

    @(
        '# Configuración local del monitor. NO subir a GitHub (está en .gitignore).'
        "TELEGRAM_BOT_TOKEN=$Token"
        "TELEGRAM_CHAT_ID=$ChatId"
        '# DISCORD_WEBHOOK_URL='
    ) | Set-Content -Path $EnvFile -Encoding UTF8
    Ok "Configuración guardada en $EnvFile (chat_id=$ChatId)"
}

# --------------------------------------------------------------------------- 4
Paso 'Enviando mensaje de prueba y guardando el estado inicial'
& $Python $Script --probar-envio
if ($LASTEXITCODE -ne 0) { throw 'Falló el mensaje de prueba: revisa el token y el chat_id en .env' }
& $Python $Script | Out-Null
Ok 'Revisa Telegram: debió llegar "mensaje de prueba".'

# --------------------------------------------------------------------------- 5
Paso "Programando la revisión cada $Minutos minutos"
$accion = New-ScheduledTaskAction -Execute $PythonW `
    -Argument "`"$Script`" --log `"$LogFile`"" -WorkingDirectory $Carpeta
$cada = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutos)
$alIniciar = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$usuario = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $NombreTarea -Action $accion -Trigger @($cada, $alIniciar) `
    -Settings $ajustes -Principal $usuario `
    -Description 'Revisa el estado de Metro de Santiago y alerta por Telegram ante cambios.' -Force | Out-Null
Ok "Tarea '$NombreTarea' creada."

Write-Host "`nListo. El monitor revisa cada $Minutos minutos mientras tu sesión de Windows esté abierta." -ForegroundColor Green
Write-Host "  Registro:      $LogFile"
Write-Host "  Estado actual: python check_metro.py --consultar"
Write-Host "  Desinstalar:   powershell -ExecutionPolicy Bypass -File .\instalar_windows.ps1 -Desinstalar"
