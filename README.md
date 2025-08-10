# 🍽️ Rezept Viewer

Eine Web-Anwendung zur Anzeige und Verwaltung von Rezepten aus einer DBF-Datei mit Docker-Support.

## 🐳 Docker Setup (Empfohlen)

### Erstmalige Einrichtung:

1. **DBF-Datei bereitstellen:**
   ```bash
   # Stelle sicher, dass Rezepte.dbf im Projektverzeichnis liegt
   ls Rezepte.dbf
   ```

2. **PostgreSQL Container starten:**
   ```bash
   docker-compose up postgres -d
   ```

3. **Einmalige DBF Migration (Docker):**
   ```bash
   # Führe die einmalige Migration im Container durch
   docker-compose --profile migrate up migrate
   ```

4. **Anwendung starten:**
   ```bash
   docker-compose up -d web
   ```

4. **Web-Interface öffnen:**
   - Öffne http://localhost:8000 in deinem Browser

### Laufender Betrieb:

```bash
# Anwendung starten
docker-compose up -d

# Logs anzeigen
docker-compose logs -f web

# Anwendung stoppen
docker-compose down

# Mit Daten-Reset (Vorsicht!)
docker-compose down -v
```

## 📁 Projektstruktur

```
rezeptviewer/
├── docker/
│   ├── Dockerfile          # Web-App Container
│   ├── Dockerfile.migrate  # Migration Container
│   └── docker-compose.prod.yml # Produktions-Overrides
├── src/
│   ├── main.py             # FastAPI Backend
│   ├── database.py         # PostgreSQL Schema
│   └── migrate_robust.py   # DBF Migration Script
├── scripts/
│   ├── deploy.sh           # Produktions-Deployment
│   └── backup.sh           # Datenbank-Backup
├── static/
│   └── frontend.html       # Web Interface
├── docker-compose.yml      # Multi-Container Setup
├── requirements.txt        # Produktions-Dependencies
├── requirements-migrate.txt # Migration-Dependencies
└── Rezepte.dbf            # Deine DBF-Datei
```

## 🛠️ Lokale Entwicklung

```bash
# Dependencies installieren
pip install -r requirements.txt

# Umgebungsvariable setzen
export DATABASE_URL="postgresql://rezepte_user:rezepte_password@localhost:5432/rezepte_db"

# Server starten
python src/main.py
```

## 📊 API Endpoints

- `GET /` - Weiterleitung zur Web-App
- `GET /recipes` - Alle Rezepte
- `GET /recipes/{id}` - Einzelnes Rezept
- `POST /recipes` - Neues Rezept erstellen
- `GET /categories` - Alle Kategorien
- `GET /recipes/category/{category}` - Rezepte nach Kategorie

## ✨ Features

- ✅ Einmalige DBF-Migration (122 Rezepte von Papa)
- ✅ PostgreSQL Datenbank mit Docker
- ✅ FastAPI REST API
- ✅ Responsive Web-Interface
- ✅ Such- und Filterfunktionen
- ✅ Neue Rezepte hinzufügen
- ✅ Vollständig containerisiert

## 🚀 Produktive Bereitstellung

### Automatisierte Bereitstellung:

```bash
# Vollständige Bereitstellung mit einem Befehl
./scripts/deploy.sh
```

Das Deploy-Script führt automatisch folgende Schritte aus:
1. Stoppt bestehende Services
2. Baut frische Docker Images
3. Startet PostgreSQL Datenbank
4. Führt bei Bedarf die DBF-Migration aus
5. Startet die Web-Anwendung
6. Verifiziert alle Services

### Manuelle Produktions-Bereitstellung:

```bash
# 1. Produktions-Konfiguration verwenden
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres

# 2. Bei erstmaliger Einrichtung: Migration durchführen
docker compose --profile migrate up migrate

# 3. Web-Service starten
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d web
```

### Datenbank-Backup:

```bash
# Automatisches Backup erstellen
./scripts/backup.sh

# Backup wiederherstellen
docker compose exec postgres psql -U rezepte_user -d rezepte_db < backups/recipe_backup_YYYYMMDD_HHMMSS.sql
```

### Produktions-Umgebung:

- Nutzt `docker-compose.prod.yml` für Produktions-Overrides
- Automatische Container-Neustarts (`restart: unless-stopped`)
- Umgebungsvariable für Datenbankpasswort (`DB_PASSWORD`)
- Persistente Datenspeicherung für Uploads und Backups

## 🔧 Technische Details

- **Backend**: Python 3.13 + FastAPI 0.115.6
- **Datenbank**: PostgreSQL 17
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Container**: Docker + Docker Compose