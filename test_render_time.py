import os
import django
from django.conf import settings
from django.template import Template, Context
from datetime import time

# Configure minimal settings
if not settings.configured:
    settings.configure(
        INSTALLED_APPS=['django.contrib.contenttypes'],
        TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates'}],
        USE_TZ=True,
    )
    django.setup()

def test_rendering():
    t = time(9, 0) # 9:00 AM
    t_pm = time(21, 0) # 9:00 PM
    
    template_str = 'Slot: {{ slot|time:"A" }} | {{ slot|time:"g:i A" }}'
    template = Template(template_str)
    
    ctx = Context({'slot': t})
    output = template.render(ctx)
    print(f"Testing 09:00 -> {output}")
    
    ctx_pm = Context({'slot': t_pm})
    output_pm = template.render(ctx_pm)
    print(f"Testing 21:00 -> {output_pm}")

if __name__ == '__main__':
    test_rendering()
