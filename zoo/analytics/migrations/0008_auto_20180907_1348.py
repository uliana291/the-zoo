# Generated by Django 2.1 on 2018-09-07 13:48

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("analytics", "0007_dependencyusage_version")]

    operations = [
        migrations.AddField(
            model_name="dependency",
            name="timestamp",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="dependencyusage",
            name="timestamp",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="dependencyusage",
            name="dependency",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="depusage",
                to="analytics.Dependency",
            ),
        ),
        migrations.AlterField(
            model_name="dependencyusage",
            name="major_version",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="dependencyusage",
            name="minor_version",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="dependencyusage",
            name="patch_version",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
