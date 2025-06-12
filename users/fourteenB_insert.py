import sys
import os

# Update Python path to include the parent directory of `users`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Log the updated Python path for debugging
print('Updated Python Path:', sys.path)

# Update Python path to include `users/testdata`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'testdata')))

# Log the Python path for debugging
print('Python Path:', sys.path)

# Update Python path to include the `TeamSchedule` directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../TeamSchedule')))

# Log the updated Python path for debugging
print('Final Python Path:', sys.path)

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ['DJANGO_SETTINGS_MODULE'] = 'teamschedule.settings'

# Initialize Django
import django
django.setup()

from users.models import User, Association, Club, Team, TeamDate
from django.contrib.auth.hashers import make_password

# Update imports to reference the correct directory
from users.testdata.fourteenB.associations import ASSOCIATIONS_DATA
from users.testdata.fourteenB.clubs import CLUBS_DATA
from users.testdata.fourteenB.teams import TEAMS_DATA
from users.testdata.fourteenB.users import USERS_DATA

# Insert associations
print("Inserting associations...")
def insert_associations():
    for association_data in ASSOCIATIONS_DATA:
        if not Association.objects.filter(name=association_data['name']).exists():
            print(f"Creating association: {association_data['name']}")
            Association.objects.create(
                name=association_data['name']
            )
        else:
            print(f"Association already exists: {association_data['name']}")

# Insert clubs
print("Inserting clubs...")
def insert_clubs():
    for club_data in CLUBS_DATA:
        association = Association.objects.filter(name=club_data['association_name']).first()
        if association and not Club.objects.filter(name=club_data['name']).exists():
            print(f"Creating club: {club_data['name']}")
            Club.objects.create(
                name=club_data['name'],
                association=association
            )
        elif not association:
            print(f"Association does not exist for club: {club_data['name']}")
        else:
            print(f"Club already exists: {club_data['name']}")

# Insert teams
print("Inserting teams...")
def insert_teams():
    for team_data in TEAMS_DATA:
        club = Club.objects.filter(name=team_data['club_name']).first()
        if club and not Team.objects.filter(name=team_data['name']).exists():
            print(f"Creating team: {team_data['name']}")
            Team.objects.create(
                name=team_data['name'],
                club=club,
                location=team_data['location'],
                age_group=team_data['age_group'],
                tier=team_data['tier'],
                season=team_data['season'],
                description=team_data['description']
            )
        elif not club:
            print(f"Club does not exist for team: {team_data['name']}")
        else:
            print(f"Team already exists: {team_data['name']}")

# Insert team dates
print("Inserting team dates...")
def insert_team_dates():
    for team_data in TEAMS_DATA:
        team = Team.objects.filter(name=team_data['name']).first()
        if team:
            # Insert home dates
            for home_date_info in team_data['home_dates']:
                date_str = home_date_info['date']
                allow_doubleheader = home_date_info['allow_doubleheader']
                if not TeamDate.objects.filter(team=team, date=date_str, is_home=True).exists():
                    print(f"Adding home date {date_str} (DH: {allow_doubleheader}) for team {team.name}")
                    TeamDate.objects.create(
                        team=team, 
                        date=date_str, 
                        is_home=True, 
                        allow_doubleheader=allow_doubleheader
                    )

            # Insert away dates
            for away_date_info in team_data['away_dates']:
                date_str = away_date_info['date']
                allow_doubleheader = away_date_info['allow_doubleheader']
                if not TeamDate.objects.filter(team=team, date=date_str, is_home=False).exists():
                    print(f"Adding away date {date_str} (DH: {allow_doubleheader}) for team {team.name}")
                    TeamDate.objects.create(
                        team=team, 
                        date=date_str, 
                        is_home=False, 
                        allow_doubleheader=allow_doubleheader
                    )

# Insert users
def insert_users():
    for user_data in USERS_DATA:
        if not User.objects.filter(email=user_data['email']).exists():
            user = User.objects.create(
                email=user_data['email'],
                username=user_data.get('username', user_data['email'].split('@')[0]),
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_active=user_data.get('is_active', True),
                is_staff=user_data.get('is_staff', False),
                is_superuser=user_data.get('is_superuser', False),
                password=make_password(user_data['password']),
            )
            user.save()

            # Add user to their respective teams by name
            team_names = user_data.get('team_names', [])
            for team_name in team_names:
                team = Team.objects.filter(name=team_name).first()
                if team:
                    team.members.add(user)
                    team.save()

# Execute insertion logic
insert_associations()
insert_clubs()
insert_teams()
insert_team_dates()
insert_users()

print("Test data successfully inserted into the development database.")
