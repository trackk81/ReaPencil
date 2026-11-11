param([string]$MayaRoot='C:\Program Files\Autodesk\Maya2025')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$qa=Join-Path $root 'native'
$build=Join-Path $env:TEMP ('ReaPencilDraw190Build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
Copy-Item -LiteralPath (Join-Path $qa 'viewport_retained190.cpp') -Destination (Join-Path $build 'viewport_retained.cpp')
$maya=$MayaRoot
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /DNT_PLUGIN /DREQUIRE_IOSTREAM /I"'+$maya+'\include" viewport_retained.cpp /link /OUT:reaPencilDraw190.mll /LIBPATH:"'+$maya+'\lib" Foundation.lib OpenMaya.lib OpenMayaUI.lib OpenMayaRender.lib /EXPORT:initializePlugin /EXPORT:uninitializePlugin'),'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try { & cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'Native build failed'} } finally {Pop-Location}
$destination=Join-Path $root 'plug-ins/2025'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $build 'reaPencilDraw190.mll') -Destination (Join-Path $destination 'reaPencilDraw190.mll')
Write-Output $build
