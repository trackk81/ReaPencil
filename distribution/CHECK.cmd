@echo off
setlocal
set "REVTOON_MAYAPY=%ProgramFiles%\Autodesk\Maya2025\bin\mayapy.exe"
if not "%~1"=="" set "REVTOON_MAYAPY=%~1"
if not exist "%REVTOON_MAYAPY%" goto missing
set "REVTOON_PACKAGE_ROOT=%~dp0"
"%REVTOON_MAYAPY%" -s -c "import os,runpy; runpy.run_path(os.path.join(os.environ['REVTOON_PACKAGE_ROOT'],'CHECK.py'),run_name='__main__')"
set "REVTOON_RESULT=%ERRORLEVEL%"
echo Results: diagnostics\report.json
pause
exit /b %REVTOON_RESULT%
:missing
echo Run: CHECK.cmd "D:\YourMaya2025\bin\mayapy.exe"
pause
exit /b 1
