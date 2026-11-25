# Gera o .exe e o instalador em dist\.  Uso: powershell -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m unittest discover tests
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; nada foi gerado." }

pyinstaller gerenciador.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

# O instalador é opcional: só gera se o Inno Setup estiver instalado.
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) { & $iscc installer\gerenciador.iss } else { Write-Warning "Inno Setup não encontrado: só o .exe foi gerado." }

Get-ChildItem dist | Select-Object Name, @{n="MB"; e={[math]::Round($_.Length/1MB,1)}}
