@echo off
echo Installing PyInstaller...
.venv\Scripts\python -m pip install pyinstaller pyinstaller-hooks-contrib

echo.
echo Building...
.venv\Scripts\python -m PyInstaller build.spec --clean

echo.
echo Done. Output is in dist\SpeedEditorCustomizer\
echo Run dist\SpeedEditorCustomizer\SpeedEditorCustomizer.exe to test.
pause
