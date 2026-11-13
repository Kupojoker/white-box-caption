@echo off
REM Builds a standalone whitebox_caption.exe (no Python needed to run it afterwards)
py -m pip install --upgrade pillow pyinstaller
py -m PyInstaller --onefile --windowed --name WhiteBoxCaption whitebox_caption.py
echo.
echo Done! Your app is at dist\WhiteBoxCaption.exe
pause
