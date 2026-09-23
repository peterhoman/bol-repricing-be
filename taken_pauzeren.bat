@echo off
echo Bol BE taken PAUZEREN (winkel dicht / vakantie)...
for %%T in ("Bol BE 1 - ochtend snelstart" "Bol BE 2 - probe starten" "Bol BE 3 - probe controleren" "Bol BE 4 - sync ronde") do schtasks /Change /TN %%T /DISABLE
echo.
echo Stand nu:
schtasks /Query /TN "Bol BE 1 - ochtend snelstart" /FO LIST | findstr /C:"Status"
schtasks /Query /TN "Bol BE 4 - sync ronde" /FO LIST | findstr /C:"Status"
echo.
echo Klaar. De vier BE-taken draaien niet meer tot je "taken_hervatten.bat" dubbelklikt.
pause
