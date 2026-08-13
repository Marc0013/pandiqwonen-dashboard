@echo off
cd /d "C:\Users\info\OneDrive\Documents\PandIQ\08 Tools en templates\00 Dashboard PandIQ wonen"

echo [%date% %time%] Dashboard update gestart >> log.txt

echo Site audit draaien...
"C:\Users\info\AppData\Local\Programs\Python\Python313\python.exe" site_audit.py >> log.txt 2>&1

echo Zoektrends ophalen...
"C:\Users\info\AppData\Local\Programs\Python\Python313\python.exe" trends.py >> log.txt 2>&1

echo Dashboard genereren en pushen...
"C:\Users\info\AppData\Local\Programs\Python\Python313\python.exe" generate_dashboard.py >> log.txt 2>&1

echo [%date% %time%] Klaar >> log.txt
