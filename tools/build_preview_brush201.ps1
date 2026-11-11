param([string]$OutputName='reaPencilPreviewBrush201b.dll')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $env:TEMP ('ReaPencilBrushCompute201_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'native/preview_brush201.cpp') -Destination (Join-Path $build 'preview_brush.cpp')
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:precise preview_brush.cpp /link /OUT:'+$OutputName),'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try { & cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'Preview compute build failed'} } finally {Pop-Location}
$destination=Join-Path $root 'plug-ins/2025'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $build $OutputName) -Destination (Join-Path $destination $OutputName)
Write-Output $build
