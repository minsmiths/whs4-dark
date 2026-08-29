<#
.SYNOPSIS
    VNC 로그인 컨테이너를 띄우고 VNC 뷰어를 자동으로 연결한다 (로드맵 M1).

.DESCRIPTION
    지금까지는 사람이 docker run 명령을 손으로 치고, VNC 뷰어도 매번 따로 실행해야 했다.
    이 스크립트가 그 두 단계를 하나로 묶는다:
      1. login.sh 컨테이너를 새 PowerShell 창에서 띄운다 (input() 프롬프트가 그 창에 뜬다)
      2. 호스트 포트는 5900 고정이 아니라 비어있는 포트를 자동으로 고른다
         (TightVNC Server 등 다른 프로그램이 5900을 이미 쓰고 있어도 충돌하지 않는다)
      3. 컨테이너가 뜨는 즉시 VNC 뷰어(TightVNC)를 그 포트로 자동 실행한다
      4. VNC 접속 비밀번호는 실행마다 새로 무작위 생성한다 (재사용/노출 방지)

    프로젝트 루트는 이 스크립트 파일의 위치를 기준으로 계산하므로, 어느 폴더에서
    실행하든 whitelist.yaml 마운트 경로가 어긋나지 않는다.

.PARAMETER SourceName
    whitelist.yaml 에 등록된 name (또는 url).

.PARAMETER Image
    사용할 Docker 이미지 태그. 기본값 darkweb-crawler:latest.

.EXAMPLE
    .\docker\vnc-login.ps1 -SourceName darkforums
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceName,
    [ValidateSet("chromium", "firefox")]
    [string]$BrowserEngine = "chromium",
    [string]$Image = "darkweb-crawler:latest",
    [string]$ViewerPath = "C:\Program Files\TightVNC\tvnviewer.exe"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WhitelistPath = Join-Path $ProjectRoot "whitelist.yaml"

if (-not (Test-Path $WhitelistPath -PathType Leaf)) {
    Write-Error "whitelist.yaml 이 없습니다: $WhitelistPath (whitelist.example.yaml을 복사해서 만들어주세요)"
    exit 1
}

# 매 실행마다 새 무작위 비밀번호 — 재사용하거나 채팅/로그에 남기지 않는다.
$VncPassword = -join ((48..57) + (97..122) | Get-Random -Count 14 | ForEach-Object { [char]$_ })
$ContainerName = "darkweb-login-$([guid]::NewGuid().ToString('N').Substring(0, 8))"

Write-Host "컨테이너 시작 중... ($ContainerName)"
Write-Host "VNC 접속 비밀번호: $VncPassword"  -ForegroundColor Yellow

# 호스트 포트를 비워서(":5900"이 아니라 "::5900") 도커가 비어있는 포트를 알아서 고르게 한다.
$dockerCmdLine = "docker run --rm -it --name $ContainerName " +
    "-p 127.0.0.1::5900 " +
    "-e VNC_PASSWORD=$VncPassword " +
    "-e BROWSER_ENGINE=$BrowserEngine " +
    "-v `"${WhitelistPath}:/app/whitelist.yaml:ro`" " +
    "-v darkweb-sessions:/app/sessions " +
    "$Image ./docker/login.sh $SourceName"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $dockerCmdLine

Write-Host "컨테이너가 뜨고 VNC 포트가 열릴 때까지 기다리는 중..."
$hostPort = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $portInfo = $null
    try { $portInfo = docker port $ContainerName 5900 2>$null } catch { }
    if ($portInfo) {
        $hostPort = ($portInfo -split ":")[-1].Trim()
        break
    }
}

if (-not $hostPort) {
    Write-Error "컨테이너 포트를 30초 안에 찾지 못했습니다. 새로 뜬 터미널 창에서 에러 메시지를 확인하세요."
    exit 1
}

if (-not (Test-Path $ViewerPath -PathType Leaf)) {
    Write-Warning "TightVNC 뷰어를 $ViewerPath 에서 찾지 못했습니다. 직접 뷰어를 열어 127.0.0.1:$hostPort 로 접속하세요."
    exit 0
}

# 이전에 뜨다 만(창 없이 멈춘) 뷰어 프로세스가 남아있으면 새 창이 안 뜨는 원인이 된다 —
# 먼저 정리한다. 그다음 창이 실제로 뜨는지(MainWindowHandle != 0) 확인하고, 안 뜨면
# 자동으로 몇 번 더 재시도한다 — 사람이 다시 요청할 필요 없이 스크립트가 스스로 되게 한다.
$viewerProcessName = [System.IO.Path]::GetFileNameWithoutExtension($ViewerPath)
Get-Process $viewerProcessName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

$viewerLaunched = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    Write-Host "VNC 뷰어를 127.0.0.1:$hostPort 로 실행합니다... (시도 $attempt/3)"
    Start-Process $ViewerPath -ArgumentList "127.0.0.1:$hostPort"
    Start-Sleep -Seconds 2

    $proc = Get-Process $viewerProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc -and $proc.MainWindowHandle -ne 0) {
        $viewerLaunched = $true
        break
    }

    Get-Process $viewerProcessName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

if ($viewerLaunched) {
    Write-Host "VNC 뷰어 창이 떴습니다." -ForegroundColor Green
}
else {
    Write-Warning "VNC 뷰어 창이 자동으로 뜨지 않았습니다. 직접 실행하세요: `"$ViewerPath`" 127.0.0.1:$hostPort"
}
