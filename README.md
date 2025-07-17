# TeamSchedule

A Django-based web application for managing sports team schedules, divisions, clubs, and associations. This application helps sports organizations coordinate team scheduling, manage member relationships, and track division calendars.

98% vibe coded over 6 weeks with VSCode and CoPilot!

## Features

- **Team Management**: Create and manage teams with member administration
- **Club System**: Organize teams under clubs with location and member tracking
- **Association Structure**: Group clubs under associations for larger organizational management
- **Division Scheduling**: Automatic schedule generation based on age groups and tiers
- **Calendar Views**: Interactive calendars for teams and divisions
- **User Roles**: Support for team admins, club admins, and association admins
- **Control Panel**: Administrative interface for superusers to manage all entities

## Technology Stack

- **Backend**: Django 5.1, Python 3.8+
- **Database**: PostgreSQL
- **Frontend**: Bootstrap 5, JavaScript
- **Authentication**: Custom email-based authentication
- **Environment Management**: django-environ

## Installation

### Prerequisites

- Python 3.8 or higher
- PostgreSQL
- Git

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd TeamSchedule
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env with your actual values
   # See Environment Configuration section below
   ```

5. **Set up PostgreSQL database**
   ```bash
   # Create database (adjust commands for your PostgreSQL setup)
   createdb teamschedule
   ```

6. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

7. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   - Open your browser to `http://localhost:8000`
   - Admin interface: `http://localhost:8000/admin`

## Environment Configuration

Create a `.env` file in the project root with the following variables:

```bash
# Django Security
SECRET_KEY=your-very-secret-key-here
DEBUG=True

# Database Configuration  
DB_NAME=teamschedule
DB_USER=postgres
DB_PASSWORD=your-database-password
DB_HOST=localhost
DB_PORT=5432

# Email Configuration (for Gmail)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password

# Allowed Hosts (comma-separated)
ALLOWED_HOSTS=localhost,127.0.0.1

# CSRF Trusted Origins (for external domains, comma-separated)
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
```

### Generating a Secret Key

To generate a new Django secret key:

```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

## Usage

### User Roles

1. **Regular Users**: Can be members of teams and clubs
2. **Team Admins**: Can manage specific teams and their schedules
3. **Club Admins**: Can manage clubs and all teams within those clubs
4. **Association Admins**: Can manage associations and all clubs/teams within
5. **Superusers**: Full access to all functionality including the control panel

### Key Workflows

1. **Creating Teams**: Navigate to Control Panel → Teams → Create Team
2. **Managing Schedules**: Teams can set availability dates for automatic scheduling
3. **Division Calendars**: View generated schedules for entire divisions
4. **Member Management**: Add users to teams, clubs, and associations

## Project Structure

```
TeamSchedule/
├── teamschedule/          # Django project settings
├── users/                 # Main application
│   ├── models.py         # Data models (User, Team, Club, Association, etc.)
│   ├── views.py          # View controllers
│   ├── forms.py          # Django forms
│   ├── templates/        # HTML templates
│   ├── services/         # Business logic services
│   └── migrations/       # Database migrations
├── static/               # Static files (CSS, JS, images)
├── requirements.txt      # Python dependencies
└── manage.py            # Django management script
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow Django best practices
- Write descriptive commit messages
- Add tests for new features
- Update documentation for any new functionality

## Production Deployment

### Security Checklist

Before deploying to production:

- [ ] Set `DEBUG=False` in environment variables
- [ ] Use a strong, unique `SECRET_KEY`
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Set up HTTPS and update `CSRF_TRUSTED_ORIGINS`
- [ ] Use environment variables for all sensitive data
- [ ] Set up proper logging and monitoring
- [ ] Configure database backups

### Deployment Steps

1. Set up your production server with Python and PostgreSQL
2. Clone the repository and set up the virtual environment
3. Configure production environment variables
4. Run migrations: `python manage.py migrate`
5. Collect static files: `python manage.py collectstatic`
6. Set up a WSGI server (Gunicorn, uWSGI)
7. Configure a reverse proxy (Nginx, Apache)
8. Set up SSL certificates

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify PostgreSQL is running
   - Check database credentials in `.env`
   - Ensure database exists

2. **Email Configuration Issues**
   - For Gmail, use an App Password, not your regular password
   - Enable 2-factor authentication and generate an app-specific password

3. **Static Files Not Loading**
   - Run `python manage.py collectstatic`
   - Check static file configuration in settings

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please open an issue on the GitHub repository or contact the development team.

## Changelog

### Version 1.0.0
- Initial release
- Team, Club, and Association management
- Division scheduling system
- User authentication and authorization
- Control panel for administrators
