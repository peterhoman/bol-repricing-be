@echo off
rem Maakt de vier BE-taken opnieuw aan (taken_aanmaken.ps1). Dubbelklikken.
rem "Uitvoeren met PowerShell" via rechtsklik werkt op deze pc niet (venster
rem gaat direct dicht); deze .bat start hetzelfde script wel.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0taken_aanmaken.ps1"
