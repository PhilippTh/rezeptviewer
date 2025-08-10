#!/bin/bash

# Production Deployment Script for Recipe Viewer
# Usage: ./deploy.sh

set -e

echo "🍽️  Recipe Viewer - Production Deployment"
echo "========================================"

# Step 1: Stop existing services
echo "📛 Stopping existing services..."
docker compose down || true

# Step 2: Build fresh images
echo "🔨 Building fresh Docker images..."
docker compose build --no-cache

# Step 3: Start database
echo "🗄️  Starting PostgreSQL database..."
docker compose up -d postgres

# Step 4: Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
timeout=30
counter=0
until docker compose exec postgres pg_isready -U rezepte_user -d rezepte_db >/dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -eq $timeout ]; then
        echo "❌ Database failed to start within $timeout seconds"
        exit 1
    fi
    echo "   Database not ready, waiting... ($counter/$timeout)"
    sleep 2
done
echo "✅ Database is ready!"

# Step 5: Check if data migration is needed
echo "🔍 Checking if data migration is needed..."
RECIPE_COUNT=$(docker compose exec postgres psql -U rezepte_user -d rezepte_db -t -c "SELECT COUNT(*) FROM recipes;" 2>/dev/null | tr -d ' \n' || echo "0")

if [ "$RECIPE_COUNT" = "0" ] || [ -z "$RECIPE_COUNT" ]; then
    echo "📥 No recipes found. Running data migration..."
    
    # Check if DBF file exists
    if [ ! -f "Rezepte.dbf" ]; then
        echo "❌ Error: Rezepte.dbf file not found!"
        echo "   Please place your Rezepte.dbf file in the project directory."
        exit 1
    fi
    
    echo "📁 Found Rezepte.dbf file"
    echo "🔄 Starting migration process..."
    
    # Run migration
    docker compose run --rm --profile migrate migrate
    
    # Verify migration
    NEW_COUNT=$(docker compose exec postgres psql -U rezepte_user -d rezepte_db -t -c "SELECT COUNT(*) FROM recipes;" 2>/dev/null | tr -d ' \n')
    echo "✅ Migration completed! Imported $NEW_COUNT recipes."
else
    echo "✅ Found $RECIPE_COUNT existing recipes. Skipping migration."
fi

# Step 6: Start web application
echo "🚀 Starting web application..."
docker compose up -d web

# Step 6b: Start nginx reverse proxy (if using production config)
if [ -f "docker/docker-compose.prod.yml" ]; then
    echo "🌐 Starting Nginx reverse proxy..."
    docker compose -f docker-compose.yml -f docker/docker-compose.prod.yml up -d nginx
fi

# Step 7: Wait for web service to be ready
echo "⏳ Waiting for web service to be ready..."
timeout=30
counter=0
# Check port 80 if nginx is running, otherwise port 8000
if docker compose ps nginx >/dev/null 2>&1 && docker compose ps nginx | grep -q "Up"; then
    CHECK_URL="http://localhost/recipes"
else
    CHECK_URL="http://localhost:8000/recipes"
fi

until curl -s "$CHECK_URL" >/dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -eq $timeout ]; then
        echo "❌ Web service failed to start within $timeout seconds"
        docker compose logs web --tail 10
        exit 1
    fi
    echo "   Web service not ready, waiting... ($counter/$timeout)"
    sleep 2
done

# Step 8: Final verification
echo "🔍 Final verification..."
FINAL_COUNT=$(curl -s "$CHECK_URL" | jq length 2>/dev/null || echo "0")
echo "✅ Web service is ready! Serving $FINAL_COUNT recipes."

echo ""
echo "🎉 Deployment completed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if docker compose ps nginx >/dev/null 2>&1 && docker compose ps nginx | grep -q "Up"; then
    echo "🌐 Recipe Viewer: http://localhost (via Nginx)"
    echo "🔒 Direct access: http://localhost:8000 (internal only)"
else
    echo "📱 Recipe Viewer: http://localhost:8000"
fi
echo "🗄️  Database: PostgreSQL 17 on port 5432"
echo "📊 Total recipes: $FINAL_COUNT"
echo ""
echo "🛠️  Management Commands:"
echo "  docker compose logs web     # View web logs"
echo "  docker compose logs postgres # View database logs"
echo "  docker compose down         # Stop all services"
echo "  docker compose restart web  # Restart web service"