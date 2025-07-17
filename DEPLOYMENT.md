# Quick Deployment Guide

## Deploy to Render (Recommended - Free Tier Available)

### One-Click Deploy
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Manual Setup

1. **Create accounts and fork repo**:
   - Sign up at [render.com](https://render.com/)
   - Fork this repository to your GitHub
   - Connect GitHub to Render

2. **Create PostgreSQL database**:
   - Render Dashboard → "New +" → "PostgreSQL"
   - Name: `teamschedule-db`
   - Plan: Free
   - Click "Create Database"

3. **Deploy web service**:
   - Render Dashboard → "New +" → "Web Service"
   - Connect your forked repo
   - Settings:
     - **Build Command**: `./build.sh`
     - **Start Command**: `gunicorn teamschedule.wsgi:application`
     - **Environment**: Python 3

4. **Environment Variables**:
   ```
   SECRET_KEY=your-secret-key-here
   DEBUG=False
   ALLOWED_HOSTS=your-app-name.onrender.com
   ```

5. **Connect Database**:
   - Web Service → Environment → "Add from Database"
   - Select your PostgreSQL database
   - This adds `DATABASE_URL` automatically

6. **Deploy**: Click "Create Web Service" and wait for deployment

### Post-Deployment

1. **Create superuser** (via Render Shell):
   ```bash
   python manage.py createsuperuser
   ```

2. **Test the application**:
   - Visit your app URL
   - Register a new account
   - Create associations, clubs, and teams

## Alternative Platforms

The app also works on:
- **Railway**: Use `Procfile` and requirements.txt
- **Heroku**: Use `Procfile` and requirements.txt  
- **DigitalOcean App Platform**: Use `Procfile`
- **PythonAnywhere**: Manual setup with requirements.txt

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | Random 50-char string |
| `DEBUG` | Debug mode | `False` |
| `DATABASE_URL` | PostgreSQL URL | Auto-provided by host |
| `ALLOWED_HOSTS` | Allowed domains | `myapp.onrender.com` |
| `EMAIL_HOST_USER` | Email (optional) | `your-email@gmail.com` |
| `EMAIL_HOST_PASSWORD` | Email password | App password |

## Files for Deployment

- `build.sh` - Render build script
- `Procfile` - Process file for Heroku/Railway
- `runtime.txt` - Python version specification
- `render.yaml` - Render service configuration
- `requirements.txt` - Python dependencies
