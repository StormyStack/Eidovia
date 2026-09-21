# 🚀 EduAR-AI Docker Quick Reference

Fast lookup for common tasks.

---

## 🎯 Most Common Commands

### Start Stack
```bash
docker-compose up -d
```

### View Status
```bash
docker-compose ps
```

### View Logs
```bash
docker-compose logs -f ai-service
```

### Stop Stack
```bash
docker-compose down
```

---

## 🔧 Configuration

### Edit Settings
```bash
notepad .env
docker-compose restart
```

### View Current Settings
```bash
cat .env
```

### Validate .env
```bash
# Check it has no "changeme" placeholders
grep changeme .env
```

---

## 🧪 Testing

### Health Check
```bash
curl http://localhost:8001/health
```

### Chat Endpoint
```bash
curl -X POST http://localhost:8001/api/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is DNA?"}'
```

### Database Connection
```bash
docker exec -it eduarai_postgres psql -U appuser -d eduarai -c "SELECT 1"
```

### Redis Connection
```bash
docker exec -it eduarai_redis redis-cli ping
```

---

## 📊 Monitoring

### All Logs
```bash
docker-compose logs -f
```

### AI Service Only
```bash
docker-compose logs -f ai-service
```

### Last 50 Lines
```bash
docker-compose logs --tail=50
```

### Watch in Real-Time
```bash
docker-compose logs -f --timestamps
```

---

## 🔄 Updates

### Rebuild AI Service
```bash
docker-compose build ai-service --no-cache
docker-compose up -d ai-service
```

### Update Dependencies
```bash
# Edit requirements.txt, then:
docker-compose build ai-service --no-cache
docker-compose restart ai-service
```

### Pull Latest Schema
```bash
git pull origin data-layer
docker-compose restart postgres
```

---

## 🐛 Troubleshooting

### Service Won't Start
```bash
docker-compose logs ai-service
# Check error message and fix .env or code
```

### Port Already in Use
```bash
# Find what's using port 8001
netstat -ano | findstr :8001
# Or change API_PORT in .env
```

### PostgreSQL Not Initializing
```bash
docker-compose logs postgres
# Common: schema file not found or invalid SQL
```

### Redis Connection Refused
```bash
docker-compose logs redis
# Check REDIS_PASSWORD in .env matches
```

### Clear Everything (DANGEROUS)
```bash
# Remove all containers and volumes
docker-compose down -v
# Restart fresh
docker-compose up -d
```

---

## 🔐 Secrets Management

### Check if .env is Safe
```bash
# Should NOT contain "changeme" or "password"
grep -i "changeme\|password=" .env | grep -v "^#"
```

### Rotate Passwords (if needed)
```bash
# 1. Edit .env with new passwords
# 2. Stop services
docker-compose down

# 3. Remove volumes (WARNING: wipes data)
docker volume rm eduarai_pgdata eduarai_redisdata

# 4. Start fresh
docker-compose up -d
```

---

## 📈 Performance

### Check Container Resource Usage
```bash
docker stats
```

### Monitor in Real-Time
```bash
docker stats --no-stream=false
```

### View Container Details
```bash
docker inspect eduarai_ai
```

---

## 🔍 Debugging

### Enter AI Service Container
```bash
docker exec -it eduarai_ai bash
```

### Run Python Interactive
```bash
docker exec -it eduarai_ai python
```

### Check Network
```bash
docker network inspect eduarai_network
```

### View All Volumes
```bash
docker volume ls
```

---

## 🗑️ Cleanup

### Stop All (Keep Data)
```bash
docker-compose stop
```

### Remove Containers (Keep Data)
```bash
docker-compose down
```

### Remove Everything (WIPES DATA)
```bash
docker-compose down -v
```

### Remove Unused Images
```bash
docker image prune -a
```

### Remove Unused Volumes
```bash
docker volume prune
```

---

## 📝 File Locations Inside Containers

### AI Service
- Code: `/app/main_service.py`
- Logs: stdout (use `docker-compose logs`)

### PostgreSQL
- Data: `/var/lib/postgresql/data`
- Config: `/etc/postgresql/`

### Redis
- Data: `/data/`
- Config: In-memory only

---

## 🎓 Learning Resources

### Docker Compose Docs
```
https://docs.docker.com/compose/
```

### Docker CLI Reference
```
https://docs.docker.com/engine/reference/commandline/docker/
```

### PostgreSQL in Docker
```
https://hub.docker.com/r/pgvector/pgvector
```

### Redis in Docker
```
https://hub.docker.com/_/redis
```

---

## ✅ Checklist Before Committing

```bash
# 1. Stop services
docker-compose stop

# 2. Check no uncommitted .env
git status
# .env should NOT be in output

# 3. Check no sensitive data in code
grep -r "password\|secret\|token" *.py | grep -v "#"

# 4. Verify .env.example has placeholders
grep "changeme" .env.example

# 5. All good? Commit
git add .
git commit -m "Week 4: AI service with Docker"
git push origin week4-postgres-integration
```

---

## 💡 Pro Tips

1. **Use `docker-compose logs -f` in a separate terminal** while developing
2. **Set `DEBUG=True` in .env** when troubleshooting
3. **Use `--no-cache` when rebuilding** if changes aren't showing up
4. **Volume changes** take effect immediately (no rebuild needed)
5. **Environment changes** require `docker-compose restart`

---

**Last Updated:** 2026-09-18
