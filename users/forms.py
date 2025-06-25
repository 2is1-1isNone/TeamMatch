from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from .models import User
from .models import Team, Schedule
from .models import Club, Association

class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'title']

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user

class TeamForm(forms.ModelForm):
    new_club_name = forms.CharField(required=False, label="Or create new club")
    new_association_name = forms.CharField(required=False, label="Or create new association")
    
    class Meta:
        model = Team
        fields = [
            'name', 'club', 'age_group', 'tier', 'season',
            'description', 'location', 'ready_for_scheduling'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ['event_type', 'title', 'rink_location', 'start_time', 'end_time']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Username or Email", 
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "placeholder": "Enter username or email"
        })
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Convert to lowercase for case-insensitive authentication
            username = username.lower()
        return username

    def clean(self):
        username_or_email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username_or_email and password:
            # First try to authenticate with the value as-is (could be username)
            self.user_cache = authenticate(self.request, username=username_or_email, password=password)
            
            # If that fails and the input looks like an email, try finding user by email
            if self.user_cache is None and '@' in username_or_email:
                try:
                    # Find user by email and try authenticating with their username
                    user = User.objects.get(email=username_or_email)
                    self.user_cache = authenticate(self.request, username=user.username, password=password)
                except User.DoesNotExist:
                    pass
            
            if self.user_cache is None:
                raise forms.ValidationError("Invalid username/email or password.")
            else:
                self.confirm_login_allowed(self.user_cache)
                
        return self.cleaned_data

class ClubForm(forms.ModelForm):
    class Meta:
        model = Club
        fields = ['name', 'association']

class AssociationForm(forms.ModelForm):
    class Meta:
        model = Association
        fields = ['name']

class SimpleRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Convert email to lowercase for case-insensitive storage
            email = email.lower()
            # Check if user already exists (case-insensitive)
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError("A user with this email address already exists.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        # Optionally set username to email or a unique value
        if not user.username:
            user.username = user.email
        if commit:
            user.save()
        return user

class UserEditForm(forms.ModelForm):
    teams = forms.ModelMultipleChoiceField(
        queryset=Team.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    admin_teams = forms.ModelMultipleChoiceField(
        queryset=Team.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Team Admin Of"
    )
    admin_clubs = forms.ModelMultipleChoiceField(
        queryset=Club.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Club Admin Of"
    )
    admin_associations = forms.ModelMultipleChoiceField(
        queryset=Association.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Association Admin Of"
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Convert email to lowercase for case-insensitive storage
            email = email.lower()
            # Check if another user has this email (case-insensitive), excluding current user
            if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("A user with this email address already exists.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['teams'].initial = self.instance.teams.all()
            self.fields['admin_teams'].initial = self.instance.admin_teams.all()
            self.fields['admin_clubs'].initial = self.instance.admin_clubs.all()
            self.fields['admin_associations'].initial = self.instance.admin_associations.all()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            # Update many-to-many relationships
            user.teams.set(self.cleaned_data['teams'])
            user.admin_teams.set(self.cleaned_data['admin_teams'])
            user.admin_clubs.set(self.cleaned_data['admin_clubs'])
            user.admin_associations.set(self.cleaned_data['admin_associations'])
        return user