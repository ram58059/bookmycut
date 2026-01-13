from django.shortcuts import render

def home(request):
    return render(request, 'core/home.html')





def hairstyle_gallery(request):
    import os
    from django.conf import settings

    directory = os.path.join(settings.BASE_DIR, 'static/img/hairstyles')
    images = []
    
    # Get all style*.jpg files
    try:
        all_files = [f for f in os.listdir(directory) if f.startswith('style') and f.endswith('.jpg')]
        # Sort naturally: style1, style2, ... style10
        all_files.sort(key=lambda x: int(x.replace('style', '').replace('.jpg', '')))
    except FileNotFoundError:
        all_files = []

    for i, filename in enumerate(all_files):
        images.append({
            'id': i + 1,
            'url': f'img/hairstyles/{filename}',
        })

    return render(request, 'core/hairstyles.html', {'images': images})




