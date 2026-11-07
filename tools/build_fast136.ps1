param([string]$MayaRoot='C:\Program Files\Autodesk\Maya2025',[string]$OutputName='reaPencilFast146.mll',[string]$SourceName='viewport_fast.cpp')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $env:TEMP ('revtoon_native_build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
Copy-Item -LiteralPath (Join-Path $root ('native\'+$SourceName)) -Destination (Join-Path $build 'viewport_draw.cpp')
Copy-Item -LiteralPath (Join-Path $root 'native/fast_edge_smooth.h') -Destination $build
Copy-Item -LiteralPath (Join-Path $root 'native/fast_edge_disk.h') -Destination $build
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),
    ('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /DNT_PLUGIN /DREQUIRE_IOSTREAM /I"'+$MayaRoot+'\include" viewport_draw.cpp /link /OUT:revToonDraw.mll /LIBPATH:"'+$MayaRoot+'\lib" osdCPU.lib Foundation.lib OpenMaya.lib OpenMayaUI.lib OpenMayaRender.lib /EXPORT:initializePlugin /EXPORT:uninitializePlugin'),
    'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try { & cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'Native build failed'} } finally {Pop-Location}
$destination=Join-Path $root 'plug-ins\2025'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $build 'revToonDraw.mll') -Destination (Join-Path $destination $OutputName)
Write-Output (Join-Path $destination $OutputName)
