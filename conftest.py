import os
import pytest
from django.db import transaction

@pytest.fixture(scope='session')
def django_db_setup(django_db_blocker):
    with django_db_blocker.unblock():
        pass
