$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$taskBuild=Join-Path $env:TEMP ('ReaPencilBrushBuild_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskBuild | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'native/cpu_brush.cpp') -Destination $taskBuild
foreach($header in @('cpu_visibility.h','cpu_profile_segments.h','cpu_brush_blend.h')){ Copy-Item -LiteralPath (Join-Path $root ('native/'+$header)) -Destination $taskBuild }
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
[IO.File]::WriteAllLines((Join-Path $taskBuild 'build.cmd'),@('@echo off',('call "'+$vcvars+'" >nul'),'cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:strict cpu_brush.cpp /link /OUT:reaPencilBrush125.dll','exit /b %errorlevel%'),[Text.Encoding]::ASCII)
Push-Location $taskBuild
try { & cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'CPU brush build failed'} } finally {Pop-Location}
Copy-Item -LiteralPath (Join-Path $taskBuild 'reaPencilBrush125.dll') -Destination (Join-Path $root 'plug-ins/2025/reaPencilBrush125.dll')
