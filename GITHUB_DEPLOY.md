# GitHub Deployment Guide

## Schritt 1: GitHub-Repository erstellen

1. Gehe zu https://github.com/new
2. **Repository Name**: `forex-bot`
3. **Description**: "EUR/USD Candlestick Signal Bot - Automatische Mustererkennung mit E-Mail-Benachrichtigungen"
4. **Private or Public**: Private (da `.env` Zugangsdaten enthält)
5. **Initialize with**: 
   - ☐ README.md (haben wir schon)
   - ☐ .gitignore (haben wir schon)
   - ☐ License (optional)
6. **Create repository**

**Dein Repo-Link wird sein:** `https://github.com/thimokappler-stack/forex-bot`

---

## Schritt 2: Lokal zu Git hinzufügen

```bash
cd C:\Users\thimo\forex-bot

# Git initialisieren (einmalig)
git init

# Remote Repository hinzufügen (ersetze USERNAME mit deinem GitHub-Nutzernamen)
git remote add origin https://github.com/thimokappler-stack/forex-bot.git

# Branch umbenennen auf "main" (GitHub Standard)
git branch -M main

# Alle Dateien hinzufügen (ausser denen in .gitignore)
git add .

# Initial commit
git commit -m "Initial commit: EUR/USD Candlestick Signal Bot

- 10 Candlestick-Muster (2-, 3-, 5-Kerzen)
- Trendfilter mit EMA(50)
- Stop-Loss & Take-Profit Berechnung
- E-Mail-Versand via Gmail
- Duplikat-Schutz mit state.json
- Backtest-Modus
- 16 Unit-Tests (pytest)
- Cron-ready für Raspberry Pi

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

# Push zum GitHub
git push -u origin main
```

---

## Schritt 3: Deploy auf Raspberry Pi

```bash
# 1. SSH zum Pi
ssh pi@dietpi.local

# 2. Repo klonen
cd /home/pi
git clone https://github.com/thimokappler-stack/forex-bot.git
cd forex-bot

# 3. .venv aufbauen
python3 -m venv .venv
source .venv/bin/activate

# 4. Dependencies
pip install -r requirements.txt

# 5. .env erstellen (nicht ins Git!)
# Kopiere .env.example und fülle mit echten Werten:
cp .env.example .env
nano .env
# Editiere:
# MAIL_USER=deine.adresse@gmail.com
# MAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
# MAIL_TO=thimo.kappler@gmail.com (oder andere Adresse)

# 6. Test ausführen
python main.py
# Sollte Logs ausgeben und ggf. bei Mustererkennung E-Mail senden

# 7. Cron-Job einrichten
crontab -e
# Füge diese Zeile am Ende ein:
# 1,16,31,46 * * * 1-5 cd /home/pi/forex-bot && .venv/bin/python main.py >> bot.log 2>&1
# Speichern: Ctrl+X, Y, Enter

# 8. Logs anschauen
tail -f bot.log
```

---

## Schritt 4: Updates vom Pi pullen

Wenn du Änderungen am Code machst (lokal oder auf GitHub):

```bash
# Lokal neue Features pushen
git add .
git commit -m "Feature: XYZ"
git push origin main

# Auf dem Pi pullen
cd /home/pi/forex-bot
git pull origin main
# (Neu starten mit: python main.py)
```

---

## Tipps für Raspberry Pi Betrieb

### Logrotation einrichten (bot.log wächst nicht endlos)

```bash
# Datei erstellen
sudo nano /etc/logrotate.d/forex-bot
```

Inhalt:
```
/home/pi/forex-bot/bot.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

Speichern: Ctrl+X, Y, Enter

### SSH-Schlüssel für GitHub (optional, aber sicherer)

Statt Passwort bei jedem git push/pull:

```bash
# Pi SSH-Key generieren
ssh-keygen -t ed25519 -C "dietpi@forex-bot"
# (Enter für alle Prompts)

# Public Key anzeigen
cat ~/.ssh/id_ed25519.pub
# Kopieren!

# Zu GitHub hinzufügen:
# GitHub Settings → SSH and GPG keys → New SSH key
# Paste und Save

# Dann clone mit SSH statt HTTPS:
git clone git@github.com:thimokappler-stack/forex-bot.git
```

### Status überprüfen

```bash
# Ist der Cron aktiv?
ps aux | grep python

# Letzte Logs
tail -50 bot.log

# Ist die .env vorhanden?
ls -la .env

# Nächste Ausführung prüfen
date  # Aktuelle Zeit
# (Bei Minute 1, 16, 31 oder 46 sollte der Bot laufen)
```

---

## Troubleshooting

### "Git command not found"
```bash
sudo apt update
sudo apt install git
```

### "Cannot connect to Gmail"
- Prüfe: `.env` existiert und hat richtige Werte
- Prüfe: 2FA auf Gmail ist aktiv
- Prüfe: App-Passwort (nicht normales Passwort) wird verwendet
- Test: `python main.py` lokal um Error zu sehen

### "yfinance returns empty"
- Netzwerkfehler, nächster Lauf versucht erneut
- Logs anschauen: `tail -f bot.log`

### Cron läuft nicht
```bash
# Cron-Logs anschauen (dietpi)
grep CRON /var/log/syslog | tail -20

# Oder einfach manuell testen:
cd /home/pi/forex-bot && .venv/bin/python main.py >> bot.log 2>&1
```

---

**Fragen?** Siehe [README.md](../README.md) für vollständige Dokumentation.
