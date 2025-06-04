from datetime import datetime
from users.models import Team, TeamDate, ScheduleProposal
from django.db.models import Q

class LeagueScheduler:
    def __init__(self, age_group, tier):
        self.age_group = age_group
        self.tier = tier
        self.teams = Team.objects.filter(age_group=age_group, tier=tier)
        self.schedule_conflicts = []

    def get_team_pairings(self):
        """Generate all required home/away pairings between teams"""
        pairings = []
        teams_list = list(self.teams)
        for i, home_team in enumerate(teams_list):
            for away_team in teams_list[i + 1:]:
                # Each team needs to play each other twice (home and away)
                pairings.append((home_team, away_team))
                pairings.append((away_team, home_team))
        return pairings

    def find_matching_dates(self, home_team, away_team):
        """Find dates that work for both teams and identify reasons for no matches"""
        home_dates = TeamDate.objects.filter(
            team=home_team, 
            is_home=True
        ).values_list('date', flat=True)
        
        away_dates = TeamDate.objects.filter(
            team=away_team, 
            is_home=False
        ).values_list('date', flat=True)

        # Find dates that work for both teams
        matching_dates = set(home_dates).intersection(set(away_dates))

        if not matching_dates:
            # Determine reasons for no matches
            home_team_needs_dates = len(home_dates) == 0
            away_team_needs_dates = len(away_dates) == 0

            return {
                'matching_dates': None,
                'home_team_needs_dates': home_team_needs_dates,
                'away_team_needs_dates': away_team_needs_dates
            }

        # Group into weekend pairs for series
        weekend_pairs = []
        sorted_dates = sorted(list(matching_dates))
        for i in range(len(sorted_dates) - 1):
            if (sorted_dates[i + 1] - sorted_dates[i]).days == 1:
                weekend_pairs.append((sorted_dates[i], sorted_dates[i + 1]))

        return {
            'matching_dates': weekend_pairs,
            'home_team_needs_dates': False,
            'away_team_needs_dates': False
        }

    def create_schedule(self):
        """Create the league schedule with strict series logic, but allow teams to play different opponents on the same weekend as long as it's not two games in one day."""
        teams = list(self.teams)
        schedule = []
        unscheduled_matches = []

        # Helper: get all possible series (adjacent Sat/Sun) from a list of dates
        def get_series(dates):
            dates = sorted(dates)
            return [
                (dates[i], dates[i+1])
                for i in range(len(dates)-1)
                if (dates[i+1] - dates[i]).days == 1
            ]

        # Build a dict of team id to available home/away series
        from users.models import TeamDate
        team_series = {}
        for team in teams:
            home_dates = sorted([d for d in TeamDate.objects.filter(team=team, is_home=True).values_list('date', flat=True)])
            away_dates = sorted([d for d in TeamDate.objects.filter(team=team, is_home=False).values_list('date', flat=True)])
            team_series[team.id] = {
                'home': get_series(home_dates),
                'away': get_series(away_dates)
            }

        # For each unique home/away pairing, schedule independently
        for home_team in teams:
            for away_team in teams:
                if home_team == away_team:
                    continue
                possible_series = [
                    s for s in team_series[home_team.id]['home']
                    if s in team_series[away_team.id]['away']
                ]
                scheduled = False
                for series in possible_series:
                    # Check if this home/away pair is already scheduled for this series
                    already_scheduled = any(
                        (m['home_team'] == home_team and m['away_team'] == away_team and series[0] in m['dates']) or
                        (m['home_team'] == home_team and m['away_team'] == away_team and series[1] in m['dates'])
                        for m in schedule
                    )
                    if not already_scheduled:
                        schedule.append({
                            'home_team': home_team,
                            'away_team': away_team,
                            'dates': series,
                            'status': 'scheduled'
                        })
                        scheduled = True
                        break
                if not scheduled:
                    home_series = team_series[home_team.id]['home']
                    away_series = team_series[away_team.id]['away']
                    if not home_series:
                        reason = f"Home team '{home_team.name}' does not have enough adjacent dates scheduled for a home series."
                    elif not away_series:
                        reason = f"Away team '{away_team.name}' does not have enough adjacent dates scheduled for an away series."
                    elif not any(s in away_series for s in home_series):
                        reason = f"No overlapping series: Home team '{home_team.name}' and away team '{away_team.name}' do not have any matching weekend series."
                    else:
                        reason = f"All possible series for this matchup are already booked by one or both teams (double-booking conflict)."
                    unscheduled_matches.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'reason': reason
                    })

        return schedule, unscheduled_matches