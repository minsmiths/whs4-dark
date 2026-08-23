<#
.SYNOPSIS
    등록된 대상으로 실제 크롤링(investigate.py)을 한 줄로 실행한다 (로드맵 M5).

.DESCRIPTION
    whitelist.yaml에서 SourceName에 해당하는 url/source_type을 직접 읽어오므로,
    TARGET_URL/SOURCE_TYPE을 손으로 옮겨 적다 오타 내는 실수를 없앤다. 프로젝트 루트는
    이 스크립트 파일의 위치를 기준으로 계산하므로, 어느 폴더에서 실행하든 whitelist.yaml/
    output 마운트 경로가 어긋나지 않는다 (전에 겪은 "mount 대상이 폴더가 아니다" 에러의
    흔한 원인이 바로 이거였다).

    주의: 이 스크립트가 쓰는 whitelist.yaml 파서는 정식 YAML 파서가 아니라 이 프로젝트의
    whitelist.example.yaml 형식에 맞춘 최소 구현이다 — 형식이 크게 벗어나면 오작동할 수 있다.

.PARAMETER SourceName
    whitelist.yaml 에 등록된 name.

.PARAMETER Image
    사용할 Docker 이미지 태그. 기본값 darkweb-crawler:latest.

.EXAMPLE
    .\docker\run-crawl.ps1 -SourceName darkforums
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceName,
    [string]$Image = "darkweb-crawler:latest"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WhitelistPath = Join-Path $ProjectRoot "whitelist.yaml"

if (-not (Test-Path $WhitelistPath -PathType Leaf)) {
    Write-Error "whitelist.yaml 이 없습니다: $WhitelistPath (whitelist.example.yaml을 복사해서 만들어주세요)"
    exit 1
}

function Get-WhitelistEntry {
    param([string]$Path, [string]$Name)
    $current = $null
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*-\s*name:\s*"?([^"#]+?)"?\s*(#.*)?$') {
            if ($current -and $current.name -eq $Name) { return $current }
            $current = [ordered]@{ name = $Matches[1].Trim() }
            continue
        }
        if ($null -ne $current) {
            if ($line -match '^\s*url:\s*"?([^"#]+?)"?\s*(#.*)?$') { $current.url = $Matches[1].Trim() }
            if ($line -match '^\s*source_type:\s*"?([^"#]+?)"?\s*(#.*)?$') { $current.source_type = $Matches[1].Trim() }
        }
    }
    if ($current -and $current.name -eq $Name) { return $current }
    return $null
}

$entry = Get-WhitelistEntry -Path $WhitelistPath -Name $SourceName
if (-not $entry -or -not $entry.url) {
    Write-Error "whitelist.yaml 에서 '$SourceName' 항목(또는 url 필드)을 찾지 못했습니다."
    exit 1
}
if (-not $entry.source_type) { $entry.source_type = "forum" }

$OutputDir = Join-Path $ProjectRoot "output"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "대상: $($entry.name) ($($entry.url), type=$($entry.source_type))"

$dockerCmdLine = "docker run --rm " +
    "-v `"${WhitelistPath}:/app/whitelist.yaml:ro`" " +
    "-v `"${OutputDir}:/app/output`" " +
    "-v darkweb-sessions:/app/sessions " +
    "-v darkweb-snapshots:/app/snapshots " +
    "-e TARGET_URL=`"$($entry.url)`" " +
    "-e SOURCE_TYPE=`"$($entry.source_type)`" " +
    "$Image"

Write-Host "크롤링 실행 중... (완료되면 output\ 폴더에 결과 MD가 생깁니다)"
Invoke-Expression $dockerCmdLine
