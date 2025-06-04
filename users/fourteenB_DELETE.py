import sys
import os

# Update Python path to include the parent directory of `users`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Update Python path to include `users/testdata`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'testdata')))

# Update Python path to include the `TeamSchedule` directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../TeamSchedule')))

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ['DJANGO_SETTINGS_MODULE'] = 'teamschedule.settings'

# Initialize Django
import django
django.setup()

from users.models import User, Association, Club, Team, TeamDate
from users.testdata.fourteenB.users import USERS_DATA
from users.testdata.fourteenB.teams import TEAMS_DATA
from users.testdata.fourteenB.clubs import CLUBS_DATA
from users.testdata.fourteenB.associations import ASSOCIATIONS_DATA

# Delete users
print("Deleting users...")
User.objects.filter(email__in=[user['email'] for user in USERS_DATA]).delete()

# Delete team dates
print("Deleting team dates...")
TeamDate.objects.filter(team__name__in=[team['name'] for team in TEAMS_DATA]).delete()

# Delete teams
print("Deleting teams...")
Team.objects.filter(name__in=[team['name'] for team in TEAMS_DATA]).delete()

# Delete clubs
print("Deleting clubs...")
Club.objects.filter(name__in=[club['name'] for club in CLUBS_DATA]).delete()

# Delete associations
print("Deleting associations...")
Association.objects.filter(name__in=[association['name'] for association in ASSOCIATIONS_DATA]).delete()

print("Test data successfully deleted.")
