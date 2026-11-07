param([string]$MayaRoot='C:\Program Files\Autodesk\Maya2025')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $env:TEMP ('revtoon_mesh_build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $build | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'native\cpu_geometry.cpp') -Destination (Join-Path $build 'cpu_geometry.cpp')
Copy-Item -LiteralPath (Join-Path $root 'native\cpu_intersections.h') -Destination (Join-Path $build 'cpu_intersections.h')
Copy-Item -LiteralPath (Join-Path $root 'native\cpu_visibility.h') -Destination (Join-Path $build 'cpu_visibility.h')
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),
    ('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:strict /I"'+$MayaRoot+'\include" cpu_geometry.cpp /link /OUT:reaPencilCPU098.dll /LIBPATH:"'+$MayaRoot+'\lib"'),
    'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $build 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $build
try { & cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'Native build failed'} } finally {Pop-Location}
$destination=Join-Path $root 'plug-ins\2025'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $build 'reaPencilCPU098.dll') -Destination $destination
Write-Output (Join-Path $destination 'reaPencilCPU098.dll')
