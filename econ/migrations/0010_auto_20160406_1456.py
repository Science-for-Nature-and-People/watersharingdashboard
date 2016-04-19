# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-04-06 19:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('econ', '0009_consumerpriceindexdata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apikey',
            name='system',
            field=models.CharField(choices=[(b'USDA NASS', b'USDA NASS'), (b'BLS', b'Bureau of Labor Statistics')], max_length=10),
        ),
        migrations.AlterField(
            model_name='cropmix',
            name='source',
            field=models.CharField(choices=[(b'CENSUS', b'Census'), (b'SURVEY', b'Survey')], default=b'CENSUS', max_length=20),
        ),
    ]