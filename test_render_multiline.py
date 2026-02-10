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

def test_rendering():
    t = time(9, 0)
    
    # Test multi-line tag which appears in the user's file
    template_str = """
    Start
    {{
        slot|time:"A"
    }}
    End
    """
    try:
        template = Template(template_str)
        ctx = Context({'slot': t})
        output = template.render(ctx)
        print(f"Multi-line output: {output}")
    except Exception as e:
        print(f"Error rendering multi-line: {e}")

if __name__ == '__main__':
    test_rendering()
