$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $env:TEMP ('reapencil_spatial159_test_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'tests/native_spatial159.cpp') -Destination $build
Copy-Item -LiteralPath (Join-Path $root 'native/line_spatial159.h') -Destination $build
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),
 'cl /nologo /O2 /MD /EHsc /std:c++17 native_spatial159.cpp /Fe:spatial159_test.exe',
 'if errorlevel 1 exit /b %errorlevel%',
 'spatial159_test.exe',
 'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'test.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try { & cmd.exe /c test.cmd; if($LASTEXITCODE -ne 0){throw 'Spatial159 native test failed'} } finally {Pop-Location}
