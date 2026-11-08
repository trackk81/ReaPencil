$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $env:TEMP ('ReaPencilSegment159Build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build|Out-Null
Copy-Item -LiteralPath (Join-Path $root 'native/cpu_segments159.cpp'),(Join-Path $root 'native/cpu_visibility.h') -Destination $build
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),'cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:strict cpu_segments159.cpp /link /OUT:reaPencilSegments159.dll','exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try{& cmd.exe /c build.cmd;if($LASTEXITCODE -ne 0){throw 'CPU segment159 build failed'}}finally{Pop-Location}
Copy-Item -LiteralPath (Join-Path $build 'reaPencilSegments159.dll') -Destination (Join-Path $root 'plug-ins/2025')
Write-Output $build
