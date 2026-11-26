$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$taskBuild=Join-Path $env:TEMP ('ReaAlpha219Build_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskBuild | Out-Null
Copy-Item -Path (Join-Path $root 'native/*.h') -Destination $taskBuild
foreach($source in @('cpu_geometry.cpp','cpu_segments159.cpp','cpu_brush.cpp')){Copy-Item -LiteralPath (Join-Path $root ('native/'+$source)) -Destination $taskBuild}
$vcvars='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$lines=@('@echo off',('call "'+$vcvars+'" >nul'))
foreach($item in @(@('cpu_geometry.cpp','reaPencilCPU221.dll'),@('cpu_segments159.cpp','reaPencilSegments221.dll'),@('cpu_brush.cpp','reaPencilBrush221.dll'))){
 $lines+=('cl /nologo /LD /O2 /MD /EHsc /std:c++17 /fp:strict '+$item[0]+' /link /OUT:'+ $item[1]);$lines+='if errorlevel 1 exit /b %errorlevel%'
}
[IO.File]::WriteAllLines((Join-Path $taskBuild 'build.cmd'),$lines,[Text.Encoding]::ASCII)
Push-Location $taskBuild
try{& cmd.exe /c build.cmd;if($LASTEXITCODE -ne 0){throw 'CPU alpha219 build failed'}}finally{Pop-Location}
foreach($name in @('reaPencilCPU221.dll','reaPencilSegments221.dll','reaPencilBrush221.dll')){Copy-Item -LiteralPath (Join-Path $taskBuild $name) -Destination (Join-Path $root 'plug-ins/2025')}
Write-Output $taskBuild
