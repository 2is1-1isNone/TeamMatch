from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('users', '0017_add_email_notification_log_type'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # Try to drop the constraint if it exists
                "ALTER TABLE users_team DROP CONSTRAINT IF EXISTS unique_team_name;",
            ],
            reverse_sql=[
                # Don't add it back - we don't want unique team names
            ]
        ),
    ]
