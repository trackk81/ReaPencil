@echo off
setlocal
set "REVTOON_MAYAPY=%ProgramFiles%\Autodesk\Maya2025\bin\mayapy.exe"
if not "%~1"=="" set "REVTOON_MAYAPY=%~1"
if not exist "%REVTOON_MAYAPY%" goto missing
echo Close Maya before installing or updating ReaPencil.
echo This installs ReaPencil and its bundled CPU accelerator offline.
echo Maya's own Python packages will not be replaced.
pause
set "REVTOON_PACKAGE_ROOT=%~dp0"
"%REVTOON_MAYAPY%" -s -c "import os,runpy; runpy.run_path(os.path.join(os.environ['REVTOON_PACKAGE_ROOT'],'SETUP.py'),run_name='__main__')"
set "REVTOON_RESULT=%ERRORLEVEL%"
if not "%REVTOON_RESULT%"=="0" echo Installation failed. See install_error.txt.
pause
exit /b %REVTOON_RESULT%
:missing
echo Maya 2025 mayapy.exe was not found.
echo Run: INSTALL.cmd "D:\YourMaya2025\bin\mayapy.exe"
pause
exit /b 1
