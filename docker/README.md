# Paper2Slides Docker Setup

This document describes how to run Paper2Slides in Docker containers.

## Requirements

- **Docker Desktop** (version 20.10 or higher)
- **Git** (for cloning the repository)
- **Minimum 4GB free RAM**

## Quick Start

### 1. Clone the Paper2Slides Repository

**Important:** Clone the Paper2Slides project in a separate folder:

```powershell
# Navigate to your desired directory (e.g., Documents)
cd C:\Users\YourUsername\Documents

# Clone the Paper2Slides project
git clone https://github.com/HKUDS/Paper2Slides.git

# Navigate to the cloned project
cd Paper2Slides
```

### 2. Copy Docker Configuration

Copy the `docker` folder from this project to the root of the cloned Paper2Slides project:

```powershell
# From the folder where the docker configuration is located
xcopy /E /I docker C:\Users\YourUsername\Documents\Paper2Slides\docker
```

Or simply copy the `docker` folder manually to the root of the Paper2Slides project.

### 3. Configure Environment Variables

Create a `.env` file in the `paper2slides/` directory based on the example:

```powershell
# Copy the example file
copy paper2slides\.env.example paper2slides\.env
```

Edit `paper2slides/.env` and add your API keys:

```env
# OpenAI API Key (optional)
OPENAI_API_KEY=your_openai_api_key_here

# DeepSeek API Key (optional)
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Gemini API Key (for image generation)
GEMINI_API_KEY=your_gemini_api_key_here

# Other settings
# ...
```

### 4. Run with Docker Compose

**Important:** Run commands from the root directory of the Paper2Slides project (not from the docker folder):

```powershell
# Navigate to the project root
cd Paper2Slides

# Start all services
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.yml down
```

### 5. Access the Application

After starting, the application will be available at:

- **Frontend (web interface)**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API documentation**: http://localhost:8000/docs

## Docker Container Structure

### Backend Container
- **Port**: 8000
- **Base**: Python 3.12-slim
- **Service**: FastAPI (uvicorn)
- **Volumes**: 
  - `../outputs` - directory for saving results
  - `../paper2slides/.env` - environment variables file

### Frontend Container
- **Port**: 5173 (mapped to 80 inside container)
- **Base**: Node.js 20 (build) + Nginx (production)
- **Service**: React + Vite application served via Nginx

## Usage

### Via Web Interface

1. Open http://localhost:5173 in your browser
2. Upload a document (PDF, Word, Excel, PowerPoint, Markdown)
3. Select style and parameters
4. Click "Generate" to create slides or posters

### Via CLI (inside container)

```powershell
# Enter the backend container
docker exec -it paper2slides-backend bash

# Run Paper2Slides command
python -m paper2slides --input paper.pdf --output slides --style doraemon --length medium
```

### Via Docker exec (without entering container)

```powershell
# Run command directly
docker exec paper2slides-backend python -m paper2slides --input /path/to/paper.pdf --output slides --style academic
```

## File Mounting

To work with files on your computer, you can:

### Option 1: Copy Files to Container

```powershell
# Copy file to container
docker cp paper.pdf paper2slides-backend:/app/

# Run processing
docker exec paper2slides-backend python -m paper2slides --input /app/paper.pdf --output slides
```

### Option 2: Mount Directory (recommended)

Add a volume to `docker/docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      - ../outputs:/app/outputs
      - ../paper2slides/.env:/app/paper2slides/.env
      - ../input_files:/app/input_files  # Add this line
```

Then place your files in `./input_files/` (in the project root) and use:

```powershell
docker exec paper2slides-backend python -m paper2slides --input /app/input_files/paper.pdf --output slides
```

## Container Management

### View Status

```powershell
docker-compose -f docker/docker-compose.yml ps
```

### View Logs

```powershell
# All services
docker-compose -f docker/docker-compose.yml logs -f

# Backend only
docker-compose -f docker/docker-compose.yml logs -f backend

# Frontend only
docker-compose -f docker/docker-compose.yml logs -f frontend
```

### Restart Services

```powershell
# Restart all services
docker-compose -f docker/docker-compose.yml restart

# Restart specific service
docker-compose -f docker/docker-compose.yml restart backend
```

### Stop and Remove

```powershell
# Stop without removing containers
docker-compose -f docker/docker-compose.yml stop

# Stop and remove containers
docker-compose -f docker/docker-compose.yml down

# Stop, remove containers and volumes
docker-compose -f docker/docker-compose.yml down -v
```

## Troubleshooting

### Issue: Containers Won't Start

**Solution:**
1. Check that Docker Desktop is running
2. Check logs: `docker-compose -f docker/docker-compose.yml logs`
3. Ensure ports 8000 and 5173 are not occupied by other applications
4. Ensure you're running commands from the Paper2Slides project root

### Issue: Frontend Cannot Connect to Backend

**Solution:**
1. Ensure both containers are running: `docker-compose -f docker/docker-compose.yml ps`
2. Check that they're on the same network: `docker network ls`
3. Check backend logs: `docker-compose -f docker/docker-compose.yml logs backend`

### Issue: API Key Errors

**Solution:**
1. Ensure the `.env` file exists at `paper2slides/.env`
2. Check that the file is properly mounted in the container
3. Check file contents: `docker exec paper2slides-backend cat /app/paper2slides/.env`

### Issue: No Disk Space

**Solution:**
1. Clean unused images: `docker system prune -a`
2. Remove old volumes: `docker volume prune`
3. Check outputs size: `docker exec paper2slides-backend du -sh /app/outputs`

## Rebuilding Images

If you've made changes to the code:

```powershell
# Rebuild without cache
docker-compose -f docker/docker-compose.yml build --no-cache

# Rebuild and restart
docker-compose -f docker/docker-compose.yml up -d --build
```

## Performance

### Windows Optimization

1. **WSL2 Backend**: Use WSL2 for better Docker performance
2. **Resources**: Allocate minimum 4GB RAM for Docker Desktop
3. **Volumes**: Use named volumes for better performance on Windows

### Docker Desktop Resource Settings

1. Open Docker Desktop
2. Go to Settings → Resources
3. Set:
   - **CPUs**: minimum 2 (recommended 4+)
   - **Memory**: minimum 4GB (recommended 8GB+)
   - **Swap**: 1GB

## Additional Commands

### View Resource Usage

```powershell
docker stats
```

### System Cleanup

```powershell
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Full cleanup (be careful!)
docker system prune -a --volumes
```

## Support

If you encounter issues:

1. Check logs: `docker-compose -f docker/docker-compose.yml logs`
2. Check container status: `docker-compose -f docker/docker-compose.yml ps`
3. Create an issue in the Paper2Slides repository on GitHub

## License

MIT License - see LICENSE file in the Paper2Slides repository.
