import os
import django
from django.conf import settings
from django.template import Template, Context
from datetime import time

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=['django.contrib.contenttypes'],
        TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates'}],
        USE_TZ=True,
    )
    django.setup()

def test_newlines():
    t = time(9, 0)
    ctx = Context({'slot': t})
    
    # CASE 1: Newline after {{
    t1 = Template('Start {{ \n slot|time:"A" }} End')
    print(f"Newline after {{: {t1.render(ctx)}")
    
    # CASE 2: Newline before }}
    t2 = Template('Start {{ slot|time:"A" \n }} End')
    print(f"Newline before }}: {t2.render(ctx)}")
    
    # CASE 3: No newlines
    t3 = Template('Start {{ slot|time:"A" }} End')
    print(f"No newlines: {t3.render(ctx)}")

if __name__ == '__main__':
    test_newlines()
