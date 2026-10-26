# Maakt de vier dagelijkse taken aan voor de Bol.com BE-automatisering.
# Eenmalig uitvoeren: rechtsklik op dit bestand > "Uitvoeren met PowerShell"
# (of vanuit PowerShell: .\taken_aanmaken.ps1)

# pythonw.exe = Python ZONDER consolevenster (sinds 21/8). Met python.exe kwam bij
# elke taak een zwart venster op; op 20/8 om 10:45 werd dat dichtgeklikt en stierf
# de probe-start na 3 s (exitcode 3221225786 = console gesloten). Zonder venster
# valt er niets dicht te klikken.
$py = "C:\Python314\pythonw.exe"
$base = "C:\Users\Avantius\OneDrive\OneDriveClaude-Code-Projecten\bol-repricing-be"

if (-not (Test-Path $py)) { Write-Host "FOUT: python niet gevonden op $py"; pause; exit 1 }
if (-not (Test-Path "$base\src\scheduled_run.py")) { Write-Host "FOUT: scheduled_run.py niet gevonden"; pause; exit 1 }

# Tijden gewijzigd 18/8: NL krijgt de vroege sloten (Peters keuze - NL is de
# belangrijkste winkel), BE verhuist naar de late. Onderlinge afstanden
# ongewijzigd: check 90 min na probe-start, sync 2 uur na de check.
$taken = @(
    @{Naam="Bol BE 1 - ochtend snelstart"; Tijd="09:00"; Arg="morning"},
    @{Naam="Bol BE 2 - probe starten";     Tijd="10:45"; Arg="probe_start"},
    @{Naam="Bol BE 3 - probe controleren"; Tijd="12:15"; Arg="probe_check"},
    @{Naam="Bol BE 4 - sync ronde";        Tijd="14:15"; Arg="sync"}
)

foreach ($t in $taken) {
    $actie = New-ScheduledTaskAction -Execute $py `
        -Argument "`"$base\src\scheduled_run.py`" $($t.Arg)" `
        -WorkingDirectory $base
    $trigger = @(New-ScheduledTaskTrigger -Daily -At $t.Tijd)
    # Starttijd ZONDER tijdzone opslaan (fix 26/10, na de eerste wintertijd).
    # New-ScheduledTaskTrigger -At slaat de tijd op met tijdzone, op deze pc
    # zelfs als wereldtijd ("...T08:00:00Z"). Windows houdt zo'n trigger op
    # hetzelfde wereldtijd-moment vast, dus sinds 25/10 liepen alle vier de
    # taken een uur te vroeg (08:00/09:45/11:15/13:15). Zonder tijdzone is het
    # "gewone kloktijd" en volgt hij zomer- en wintertijd vanzelf.
    # Ligt de tijd van vandaag al achter ons, dan pas morgen beginnen: anders
    # start -StartWhenAvailable de "gemiste" run meteen na het registreren.
    # (Overgenomen van NL, instructie-BE-taakplanner-wintertijd.md.)
    foreach ($tr in $trigger) {
        $start = [datetime]$tr.StartBoundary
        if ($start -lt (Get-Date)) { $start = $start.AddDays(1) }
        $tr.StartBoundary = $start.ToString("yyyy-MM-dd'T'HH:mm:ss")
    }
    # -WakeToRun: haalt de pc uit de slaapstand voor deze taak
    # -StartWhenAvailable: draait alsnog als het tijdstip gemist werd (pc was uit)
    $instellingen = New-ScheduledTaskSettingsSet -WakeToRun `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $t.Naam -Action $actie `
        -Trigger $trigger -Settings $instellingen -Force | Out-Null
    Write-Host "Aangemaakt: $($t.Naam)  om $($t.Tijd)"
}

Write-Host ""
Write-Host "Klaar. Controle:"
Get-ScheduledTask -TaskName "Bol BE*" | Select-Object TaskName, State,
    @{N="Starttijd"; E={$_.Triggers[0].StartBoundary}} | Format-Table -AutoSize
Write-Host "Goed = starttijd ZONDER +01:00, +02:00 of Z erachter."

# Geen automatische teststart meer (weggehaald 18/8, aanbeveling NL): bij een
# her-registratie vuurde die elke keer een extra snelstart af - onnodige
# scraping op een willekeurig moment. De taken zijn al bewezen werkend.
Write-Host ""
Write-Host "Sluit dit venster. De taken draaien vanaf nu op de nieuwe tijden."
pause
