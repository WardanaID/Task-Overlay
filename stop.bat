@echo off
echo Menghentikan Antigravity Task Overlay...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq Antigravity Task Overlay*" 2>nul
taskkill /F /FI "COMMANDLINE eq *main.py*" 2>nul
wmic process where "name='pythonw.exe' and commandline like '%%main.py%%'" call terminate 2>nul
echo Selesai.

