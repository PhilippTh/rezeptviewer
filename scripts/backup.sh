#!/bin/bash

# Database Backup Script for Recipe Viewer
# Usage: ./backup.sh

set -e

BACKUP_DIR="./backups"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="recipe_backup_${DATE}.sql"

echo "📦 Recipe Database Backup"
echo "========================="

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if database is running
if ! docker compose exec postgres pg_isready -U rezepte_user -d rezepte_db >/dev/null 2>&1; then
    echo "❌ Database is not running!"
    echo "   Start it with: docker compose up -d postgres"
    exit 1
fi

echo "🔄 Creating database backup..."

# Create SQL backup
docker compose exec postgres pg_dump \
    -U rezepte_user \
    -d rezepte_db \
    --verbose \
    --no-password \
    --format=custom \
    --compress=9 \
    > "$BACKUP_DIR/$BACKUP_FILE.custom"

# Also create plain SQL backup for easier inspection
docker compose exec postgres pg_dump \
    -U rezepte_user \
    -d rezepte_db \
    --no-password \
    --format=plain \
    --inserts \
    > "$BACKUP_DIR/$BACKUP_FILE"

echo "✅ Backup completed!"
echo "📁 Files created:"
echo "   $BACKUP_DIR/$BACKUP_FILE (Plain SQL)"
echo "   $BACKUP_DIR/$BACKUP_FILE.custom (Compressed)"

# Show backup info
RECIPE_COUNT=$(docker compose exec postgres psql -U rezepte_user -d rezepte_db -t -c "SELECT COUNT(*) FROM recipes;" | tr -d ' \n')
BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
BACKUP_SIZE_CUSTOM=$(du -h "$BACKUP_DIR/$BACKUP_FILE.custom" | cut -f1)

echo ""
echo "📊 Backup Summary:"
echo "   Recipes: $RECIPE_COUNT"
echo "   SQL Size: $BACKUP_SIZE"
echo "   Compressed Size: $BACKUP_SIZE_CUSTOM"
echo ""
echo "🔄 To restore from backup:"
echo "   docker compose exec postgres psql -U rezepte_user -d rezepte_db < $BACKUP_DIR/$BACKUP_FILE"