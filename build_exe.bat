@echo off
setlocal
echo ============================================
echo  Building VoiceIsolator.exe (one-time setup)
echo ============================================
echo.
echo This needs Python 3.10 or 3.11 installed once, from python.org.
echo After this finishes you'll have a standalone .exe that needs
echo nothing else installed, ever - you can delete this whole folder
echo except the .exe afterward, or copy just the .exe to another PC.
echo.
pause

py -3.11 -m venv build_venv 2>nul || py -3.10 -m venv build_venv
if not exist build_venv (
    echo Could not find Python 3.10 or 3.11. Install one from python.org and re-run this.
    pause
    exit /b 1
)

call build_venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Packaging (this can take several minutes, torch is large)...
echo.

pyinstaller --onefile --console --name VoiceIsolator ^
    --collect-all df ^
    --collect-all libdf ^
    --collect-all torch ^
    --hidden-import sounddevice ^
    app.py

echo.
if exist dist\VoiceIsolator.exe (
    echo Done. Your standalone app is at: dist\VoiceIsolator.exe
    echo Double-click it to run - it will ask you simple questions
    echo to set itself up, no command line needed.
) else (
    echo Something went wrong - scroll up for the PyInstaller error.
    echo Common fix: re-run this script, PyInstaller sometimes needs a
    echo second pass the first time it caches torch's files.
)
pause
