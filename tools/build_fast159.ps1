param([string]$OutputName='reaPencilFast159.mll')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$taskBuild=Join-Path $env:TEMP ('ReaPencilFast159Build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskBuild | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'native/viewport_fast159.cpp') -Destination (Join-Path $taskBuild 'viewport_draw.cpp')
foreach($file in @('fast_edge_smooth.h','fast_edge_disk.h','line_spatial159.h','fast_gpu159.h')){Copy-Item -LiteralPath (Join-Path $root ('native/'+$file)) -Destination $taskBuild}
$mayaRoot='C:/Program Files/Autodesk/Maya2025'
$vcvars='C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'),('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /DNT_PLUGIN /DREQUIRE_IOSTREAM /I"'+$mayaRoot+'/include" viewport_draw.cpp /link /OUT:fast159.mll /LIBPATH:"'+$mayaRoot+'/lib" osdCPU.lib Foundation.lib OpenMaya.lib OpenMayaUI.lib OpenMayaRender.lib /EXPORT:initializePlugin /EXPORT:uninitializePlugin'),'exit /b %errorlevel%')
[IO.File]::WriteAllLines((Join-Path $taskBuild 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $taskBuild
try {& cmd.exe /c build.cmd; if($LASTEXITCODE -ne 0){throw 'Fast159 build failed'}}finally{Pop-Location}
Copy-Item -LiteralPath (Join-Path $taskBuild 'fast159.mll') -Destination (Join-Path $root ('plug-ins/2025/'+$OutputName))
