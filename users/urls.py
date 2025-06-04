from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
from .forms import EmailAuthenticationForm

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('team/new/', views.team_profile, name='team_profile_create'),
    path('accounts/login/', auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm), name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),  # <-- Add this line
    path('team/<int:team_id>/delete/', views.delete_team, name='delete_team'),
    path('all_teams/', views.all_teams, name='all_teams'),
    path('users/', views.users_list, name='users'),
    path('billing/', views.billing, name='billing'),
    path('team/<int:team_id>/calendar/', views.team_calendar, name='team_calendar'),
    path('team/<int:team_id>/edit/', views.edit_team, name='edit_team'),
    path('team/<int:team_id>/invite/', views.invite_member, name='invite_member'),
    path('team/<int:team_id>/', views.team_profile, name='team_profile'),
    path('team/<int:team_id>/page/', views.team_page, name='team_page'),
    path('control_plane/', views.control_plane, name='control_plane'),
    path('make_team_admin/', views.make_team_admin, name='make_team_admin'),
    path('make_club_admin/', views.make_club_admin, name='make_club_admin'),
    path('make_association_admin/', views.make_association_admin, name='make_association_admin'),
    path('user/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('user/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('club/<int:club_id>/edit/', views.edit_club, name='edit_club'),
    path('club/<int:club_id>/delete/', views.delete_club, name='delete_club'),
    path('association/<int:association_id>/edit/', views.edit_association, name='edit_association'),
    path('association/<int:association_id>/delete/', views.delete_association, name='delete_association'),
    path('team/<int:team_id>/save-dates/', views.save_team_dates, name='save_team_dates'),
    path('league-schedule/<str:age_group>/<str:tier>/', 
        views.generate_league_schedule, 
        name='league_schedule'),
    path('generate-schedule/<str:age_group>/<str:tier>/', views.generate_schedule_service, name='generate_schedule_service'),
    path('league-calendar/<str:age_group>/<str:tier>/', views.league_calendar, name='league_calendar'),
]