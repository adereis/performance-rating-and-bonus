# Docker Deployment

Run the Performance Rating System using Docker for easier deployment and isolation.

## Quick Start

```bash
# Build and start the container
docker-compose up -d

# Open browser to http://localhost:5000

# Generate sample data (run in container)
docker-compose exec app python3 scripts/create_sample_data.py

# Import sample data via the web interface (Import tab)
```

## Common Commands

```bash
# Start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Run commands inside container
docker-compose exec app python3 scripts/create_sample_data.py

# Access shell in container
docker-compose exec app bash
```

## Data Persistence

The database (`ratings.db`) is stored in the `./data` directory, which is mounted as a volume. This ensures your data persists even if you rebuild or remove the container.

**Important**: The `./data` directory contains your database and should be backed up regularly. It's automatically created on first run.

## Production Deployment

For production use:

1. **Remove development volume mount** in `docker-compose.yml`:
   ```yaml
   # Comment out or remove this line:
   # - .:/app
   ```

2. **Set production environment**:
   ```yaml
   environment:
     - FLASK_ENV=production
   ```

3. **Use a reverse proxy** (nginx, Traefik) for HTTPS and domain routing

4. **Set up regular backups** of the `./data` directory

## Without Docker Compose

If you prefer to use Docker directly:

```bash
# Build the image
docker build -t performance-rating-app .

# Run the container
docker run -d \
  --name performance-rating-app \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e DATABASE_URL=sqlite:////app/data/ratings.db \
  performance-rating-app

# View logs
docker logs -f performance-rating-app
```
