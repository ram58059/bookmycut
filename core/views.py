from django.shortcuts import render

def home(request):
    return render(request, 'core/home.html')

from django.shortcuts import redirect

def quick_book(request):
    service_id = request.POST.get('service_id') or request.GET.get('service_id')
    if service_id:
        request.session['selected_service_ids'] = [str(service_id)]
        request.session['selected_gender'] = 'Boy' # Default to Boy/Men for these services since they're for generic use
        return redirect('date_time_selection')
    return redirect('home')


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




    return render(request, 'core/hairstyles.html', {'images': images})

def terms(request):
    return render(request, 'policies/terms.html')

def privacy(request):
    return render(request, 'policies/privacy.html')
