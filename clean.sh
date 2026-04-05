#!/bin/bash
# Fix script for Tempo port conflict
echo "=== Fixing Tempo port 4317 conflict ==="

# 1. Stop with force and longer grace period
docker-compose stop -t 30 tempo

# 2. Kill any remaining tempo processes in containers
for container in $(docker ps -aq --filter "name=tempo"); do
    echo "Checking container $container..."
    docker exec $container pkill -9 -f "tempo|grpc" 2>/dev/null || true
done

# 3. Force remove
docker-compose rm -f tempo

# 4. Clean Docker network
docker network prune -f

# 5. Remove tempo volume (optional - will lose trace data)
# docker volume rm $(docker volume ls -q | grep tempo) 2>/dev/null || true

# 6. Start with longer healthcheck timeout
echo "Starting Tempo with extended healthcheck..."
docker-compose up -d tempo

# 7. Wait and check logs
sleep 5
echo "=== Checking Tempo logs ==="
docker-compose logs --tail=50 tempo
