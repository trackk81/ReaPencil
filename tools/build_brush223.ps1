$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$taskBuild=Join-Path $env:TEMP ('ReaBrush223Build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskBuild | Out-Null
Copy-Item -Path (Join-Path $root 'native/*.h') -Destination $taskBuild
Copy-Item -LiteralPath (Join-Path $root 'native/cpu_brush.cpp') -Destination $taskBuild
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
[IO.File]::WriteAllLines((Join-Path $taskBuild 'build.cmd'),@('@echo off',('call "'+$vcvars+'" >nul'),'cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:strict cpu_brush.cpp /link /OUT:reaPencilBrush223.dll','exit /b %errorlevel%'),[Text.Encoding]::ASCII)
Push-Location $taskBuild
try{& cmd.exe /c build.cmd;if($LASTEXITCODE -ne 0){throw 'CPU brush223 build failed'}}finally{Pop-Location}
Copy-Item -LiteralPath (Join-Path $taskBuild 'reaPencilBrush223.dll') -Destination (Join-Path $root 'plug-ins/2025')
Write-Output $taskBuild
