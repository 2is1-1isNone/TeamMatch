from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.views.decorators.http import require_http_methods  # Add this line
from .models import User, Team, Club, Association, Schedule, TeamInvite, TeamDate
from .forms import (
    CustomUserCreationForm, TeamForm, ScheduleForm, 
    ClubForm, AssociationForm, SimpleRegistrationForm,
    UserEditForm  # Add this import
)
from django.core.mail import send_mail  # At the top if you want to send real emails
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse
import json
from datetime import datetime
from users.services.schedule_service import LeagueScheduler
from django.utils.dateformat import format as date_format

def register(request):
    if request.method == 'POST':
        form = SimpleRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.backend = settings.AUTHENTICATION_BACKENDS[0]
            login(request, user)
            # Assign to teams if invited
            invites = TeamInvite.objects.filter(email=user.email, accepted=False)
            for invite in invites:
                invite.team.members.add(user)
                invite.accepted = True
                invite.save()
            return redirect('dashboard')
    else:
        form = SimpleRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

def home(request):
    return render(request, 'users/home.html')

@login_required
def dashboard(request):
    teams = request.user.teams.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    
    return render(request, 'users/dashboard.html', {
        'user': request.user,
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers
    })

@login_required
def team_profile(request, team_id=None):
    team = None
    if team_id is not None:
        team = get_object_or_404(Team, id=team_id)
    associations = Association.objects.all()
    clubs = Club.objects.all()
    teams = Team.objects.all()
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    if request.method == 'POST':
        # Get association: either existing or new
        association_id = request.POST.get('association')
        new_association_name = request.POST.get('new_association_name')
        if new_association_name:
            association, created = Association.objects.get_or_create(name=new_association_name)
            if created:
                association.admins.add(request.user)  # Make creator admin
        elif association_id:
            association = Association.objects.get(id=association_id)
        else:
            association = None

        # Get club: either existing or new (similar logic if you want)
        club_id = request.POST.get('club')
        new_club_name = request.POST.get('new_club_name')
        if new_club_name and association:
            club, created = Club.objects.get_or_create(name=new_club_name, association=association)
            if created:
                club.admins.add(request.user)  # Make creator admin
        elif club_id:
            club = Club.objects.get(id=club_id)
        else:
            club = None

        # Team: either select existing or create new
        team_id = request.POST.get('team')
        if team_id:
            team = Team.objects.get(id=team_id)
        else:
            team_name = request.POST.get('team_name')
            age_group = request.POST.get('age_group')
            tier = request.POST.get('tier')
            season = request.POST.get('season')
            description = request.POST.get('description')
            location = request.POST.get('location')
            ready_for_scheduling = bool(request.POST.get('ready_for_scheduling'))

            team = Team.objects.create(
                name=team_name,
                club=club,
                association=association,
                age_group=age_group,
                tier=tier,
                season=season,
                description=description,
                location=location,
                ready_for_scheduling=ready_for_scheduling,
            )
            team.members.add(request.user)
            team.admins.add(request.user)

        # New code for handling invites
        if not team_id:
            invite_emails = request.POST.get('invite_emails', '')
            for email in [e.strip() for e in invite_emails.split(',') if e.strip()]:
                # Create a TeamInvite object (see below)
                TeamInvite.objects.create(team=team, email=email)
                # Optionally send an email invite here

        return redirect('dashboard')

    return render(request, 'users/team_profile.html', {
        'team': team,
        'associations': associations,
        'clubs': clubs,
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        # ...other context...
    })

@login_required
def create_schedule(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    # Ensure the user is a member of the team
    if request.user not in team.members.all():
        messages.error(request, "You do not have permission to create a schedule for this team.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.team = team
            schedule.save()
            messages.success(request, 'Schedule created successfully!')
            return redirect('dashboard')
    else:
        form = ScheduleForm()
    return render(request, 'users/create_schedule.html', {'form': form, 'team': team})

from django.shortcuts import render, get_object_or_404
from .models import Team


@login_required
def delete_team(request, team_id):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('dashboard')
    
    team = get_object_or_404(Team, id=team_id)
    team.delete()
    messages.success(request, f"Team {team.name} deleted successfully.")
    
    # Get return tab from query params
    return_tab = request.GET.get('return_tab', 'users')
    return redirect(f'/control_plane/#{return_tab}')

@login_required
def all_teams(request):
    age_group = request.GET.get('age_group')
    tier = request.GET.get('tier')
    teams = Team.objects.all()
    if age_group:
        teams = teams.filter(age_group=age_group)
    if tier:
        teams = teams.filter(tier=tier)
    age_groups = Team._meta.get_field('age_group').choices
    tiers = Team._meta.get_field('tier').choices
    return render(request, 'users/all_teams.html', {
        'teams': teams,
        'age_groups': age_groups,
        'tiers': tiers,
        'selected_age_group': age_group,
        'selected_tier': tier,
    })

@login_required
def users_list(request):
    from .models import User
    users = User.objects.all()
    return render(request, 'users/users_list.html', {'users': users})

@login_required
def billing(request):
    return render(request, 'users/billing.html')

@login_required
def team_calendar(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Get existing dates
    team_dates = TeamDate.objects.filter(team=team)
    team_dates_json = [
        {
            'title': 'Home Game' if date.is_home else 'Away Game',
            'start': date.date.strftime('%Y-%m-%d'),
            'allDay': True,
            'color': '#0d6efd' if date.is_home else '#ffb366'
        } for date in team_dates
    ]
    
    context = {
        'team': team,
        'team_dates_json': json.dumps(team_dates_json)
    }
    return render(request, 'users/team_calendar.html', context)

@login_required
@require_http_methods(["POST"])
def save_team_dates(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    data = json.loads(request.body)
    date_str = data.get('date')
    is_home = data.get('is_home')
    
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if is_home is None:
            # Delete the date
            TeamDate.objects.filter(team=team, date=date_obj).delete()
        else:
            # Create or update the date
            TeamDate.objects.update_or_create(
                team=team,
                date=date_obj,
                defaults={'is_home': is_home}
            )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def edit_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if request.user not in team.admins.all():
        messages.error(request, "You do not have permission to edit this team.")
        return redirect('team_profile', team_id=team.id)
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, "Team updated successfully.")
            return redirect('team_profile', team_id=team.id)
    else:
        form = TeamForm(instance=team)
    return render(request, 'users/edit_team.html', {'form': form, 'team': team})

@login_required
def invite_member(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if request.user not in team.admins.all():
        messages.error(request, "You do not have permission to invite members.")
        return redirect('team_profile', team_id=team.id)
    if request.method == 'POST':
        email = request.POST.get('email')
        # Here you would send an invite email and/or create a pending invitation
        # For now, just show a message
        messages.success(request, f"Invitation sent to {email} (feature stub).")
        # Optionally: send_mail(subject, message, from_email, [email])
    return redirect('team_profile', team_id=team.id)

@login_required
def create_club(request):
    if request.method == 'POST':
        form = ClubForm(request.POST)
        if form.is_valid():
            club = form.save()
            club.admins.add(request.user)  # Make creator admin
            return redirect('dashboard')
    else:
        form = ClubForm()
    return render(request, 'users/create_club.html', {'form': form})

@login_required
def create_association(request):
    if request.method == 'POST':
        form = AssociationForm(request.POST)
        if form.is_valid():
            association = form.save()
            association.admins.add(request.user)  # Make creator admin
            return redirect('dashboard')
    else:
        form = AssociationForm()
    return render(request, 'users/create_association.html', {'form': form})

@staff_member_required  # Only superusers/staff can access
def control_plane(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('dashboard')

    users = User.objects.all().prefetch_related(
        'admin_teams',
        'admin_clubs',
        'admin_associations'
    )

    teams = Team.objects.all().select_related('club', 'association')
    clubs = Club.objects.all().select_related('association')
    associations = Association.objects.all()

    users_data = [{
        'user': user,
        'team_admin': user.admin_teams.all(),
        'club_admin': user.admin_clubs.all(),
        'association_admin': user.admin_associations.all(),
    } for user in users]

    return render(request, 'users/control_plane.html', {
        'users_data': users_data,
        'teams': teams,
        'clubs': clubs,
        'associations': associations
    })

@staff_member_required
@csrf_exempt
def make_team_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        team_id = request.POST.get('team_id')
        user = User.objects.get(id=user_id)
        team = Team.objects.get(id=team_id)
        team.admins.add(user)
        messages.success(request, f"{user} is now a team admin for {team.name}.")
    return redirect('control_plane')

@staff_member_required
@csrf_exempt
def make_club_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        club_id = request.POST.get('club_id')
        user = User.objects.get(id=user_id)
        club = Club.objects.get(id=club_id)
        club.admins.add(user)
        messages.success(request, f"{user} is now a club admin for {club.name}.")
    return redirect('control_plane')

@staff_member_required
@csrf_exempt
def make_association_admin(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        association_id = request.POST.get('association_id')
        user = User.objects.get(id=user_id)
        association = Association.objects.get(id=association_id)
        association.admins.add(user)
        messages.success(request, f"{user} is now an association admin for {association.name}.")
    return redirect('control_plane')

@staff_member_required
def edit_user(request, user_id):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()  # This will now properly save all relationships
            messages.success(request, f"User {user.email} updated successfully.")
            return redirect('control_plane')
    else:
        form = UserEditForm(instance=user)
    
    return render(request, 'users/edit_user.html', {
        'form': form,
        'edit_user': user
    })

@staff_member_required
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        user.delete()
        messages.success(request, "User deleted.")
        return redirect('control_plane')
    return render(request, 'users/delete_user_confirm.html', {'user': user})

@login_required
def team_page(request, team_id):
    """Display the public team page with basic info"""
    team = get_object_or_404(Team, id=team_id)
    context = {
        'team': team,
        'members': team.members.all(),
        'admins': team.admins.all()
    }
    return render(request, 'users/team_page.html', context)

@login_required
def edit_club(request, club_id):
    """Edit club details"""
    club = get_object_or_404(Club, id=club_id)
    
    # Check if user has permission
    if request.user not in club.admins.all():
        messages.error(request, "You don't have permission to edit this club.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ClubForm(request.POST, instance=club)
        if form.is_valid():
            form.save()
            messages.success(request, 'Club updated successfully.')
            return redirect('dashboard')
    else:
        form = ClubForm(instance=club)
    
    return render(request, 'users/edit_club.html', {
        'form': form,
        'club': club
    })

@login_required
def delete_club(request, club_id):
    """Delete a club and redirect to the control plane with the Clubs tab active"""
    club = get_object_or_404(Club, id=club_id)

    # Check if user has permission or is a superuser
    if not request.user.is_superuser and request.user not in club.admins.all():
        messages.error(request, "You don't have permission to delete this club.")
        return redirect('dashboard')

    if request.method == 'POST':
        club_name = club.name
        club.delete()
        messages.success(request, f'Club "{club_name}" has been deleted.')
        return redirect('/control_plane/?return_tab=clubs')

    return render(request, 'users/delete_club.html', {'club': club})

@login_required
def edit_association(request, association_id):
    """Edit an association's details"""
    association = get_object_or_404(Association, id=association_id)
    
    # Check if user has permission
    if request.user not in association.admins.all():
        messages.error(request, "You don't have permission to edit this association.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AssociationForm(request.POST, instance=association)
        if form.is_valid():
            form.save()
            messages.success(request, 'Association updated successfully.')
            return redirect('dashboard')
    else:
        form = AssociationForm(instance=association)
    
    return render(request, 'users/edit_association.html', {
        'form': form,
        'association': association
    })

@login_required
def delete_association(request, association_id):
    """Handle deletion of an association"""
    association = get_object_or_404(Association, id=association_id)
    
    # Check if user has permission
    if request.user not in association.admins.all():
        messages.error(request, "You don't have permission to delete this association.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        association_name = association.name
        association.delete()
        messages.success(request, f'Association "{association_name}" has been deleted.')
        return redirect('dashboard')
    
    return render(request, 'users/delete_association.html', {'association': association})


@login_required
def generate_league_schedule(request, age_group, tier):
    # Get the association based on the teams in this league
    teams = Team.objects.filter(age_group=age_group, tier=tier)
    if not teams.exists():
        messages.error(request, "No teams found for this league")
        return redirect('dashboard')
        
    # Get association from first team's club
    association = teams.first().club.association
    
    # Check if user is an association admin
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access the league scheduler")
        return redirect('dashboard')
    
    scheduler = LeagueScheduler(age_group, tier)
    schedule, unscheduled_matches = scheduler.create_schedule()
    
    # New code to include teams' availability dates
    teams_with_availability = []
    for team in teams:
        home_dates = TeamDate.objects.filter(team=team, is_home=True).values_list('date', flat=True)
        away_dates = TeamDate.objects.filter(team=team, is_home=False).values_list('date', flat=True)
        teams_with_availability.append({
            'team': team,
            'home_dates': home_dates,
            'away_dates': away_dates
        })

    if unscheduled_matches:
        messages.warning(
            request, 
            f"Schedule generated with {len(unscheduled_matches)} conflicts that need resolution"
        )
    
    return render(request, 'users/league_schedule.html', {
        'schedule': schedule,
        'unscheduled_matches': unscheduled_matches,
        'age_group': age_group,
        'tier': tier,
        'association': association,
        'teams_with_availability': teams_with_availability
    })

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def generate_schedule_service(request, age_group, tier):
    try:
        # Debugging session data
        session_data = dict(request.session.items())
        print("Session Data:", session_data)

        # Debugging CSRF token
        csrf_token = request.META.get('CSRF_COOKIE')
        print("CSRF Token:", csrf_token)

        # Debugging user authentication
        user_authenticated = request.user.is_authenticated
        print("User authenticated:", user_authenticated)
        print("User:", request.user)

        scheduler = LeagueScheduler(age_group, tier)
        schedule, unscheduled_matches = scheduler.create_schedule()

        if unscheduled_matches:
            messages.warning(
                request,
                f"Schedule generated with {len(unscheduled_matches)} unscheduled matches that need resolution"
            )

        return render(request, 'users/league_schedule.html', {
            'schedule': schedule,
            'unscheduled_matches': unscheduled_matches,
            'age_group': age_group,
            'tier': tier,
            'error': None,
            'debug_info': {
                'session_data': session_data,
                'csrf_token': csrf_token,
                'user_authenticated': user_authenticated,
                'user': str(request.user),
                'conflicts_count': len(unscheduled_matches) if unscheduled_matches else 0
            }
        })
    except Exception as e:
        error_message = str(e)
        print("Error:", error_message)
        return render(request, 'users/league_schedule.html', {
            'schedule': None,
            'unscheduled_matches': None,
            'age_group': age_group,
            'tier': tier,
            'error': error_message,
            'debug_info': {
                'session_data': session_data,
                'csrf_token': csrf_token,
                'user_authenticated': user_authenticated,
                'user': str(request.user),
                'error_message': error_message
            }
        })

@login_required
def league_calendar(request, age_group, tier):
    teams = Team.objects.filter(age_group=age_group, tier=tier)
    if not teams.exists():
        messages.error(request, "No teams found for this league")
        return redirect('dashboard')
    association = teams.first().club.association
    if request.user not in association.admins.all():
        messages.error(request, "You must be an association admin to access the league calendar")
        return redirect('dashboard')
    scheduler = LeagueScheduler(age_group, tier)
    schedule, _ = scheduler.create_schedule()
    # Serialize schedule to JSON for FullCalendar
    events = []
    for match in schedule:
        event = {
            'title': f"{match['home_team'].name} vs {match['away_team'].name}",
            'start': date_format(match['dates'][0], 'Y-m-d'),
            'allDay': True,
            'extendedProps': {
                'home': match['home_team'].name,
                'away': match['away_team'].name
            }
        }
        if len(match['dates']) > 1:
            # FullCalendar expects end to be exclusive, so add one day
            from datetime import timedelta
            end_date = match['dates'][1] + timedelta(days=1)
            event['end'] = date_format(end_date, 'Y-m-d')
        events.append(event)
    events_json = json.dumps(events)
    return render(request, 'users/league_calendar.html', {
        'schedule': schedule,
        'association': association,
        'age_group': age_group,
        'tier': tier,
        'events_json': events_json
    })