#!/usr/bin/env python
"""Ballava's command line.  Common commands:

    python manage.py runserver            start the app at http://localhost:8000
    python manage.py migrate              create or update the database tables
    python manage.py createsuperuser      create an admin login
    python manage.py changepassword NAME  set a new admin password
"""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
