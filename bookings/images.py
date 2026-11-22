from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile

ALLOWED_IMAGE_CONTENT_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def service_image_upload_to(instance, filename):
    # Cloudinary also prefixes MEDIA_URL ("media/"), so this lands in media/services/services/.
    return _stable_upload_path('services/services', 'service', instance, filename)


def combo_image_upload_to(instance, filename):
    return _stable_upload_path('combo_offers', 'combo', instance, filename)


def _stable_upload_path(folder, prefix, instance, filename):
    """Same path for every upload of this record, so Cloudinary overwrites it."""
    ext = 'jpg'
    if filename and '.' in filename:
        candidate = filename.rsplit('.', 1)[-1].lower()
        if candidate in {'jpg', 'jpeg', 'png', 'webp', 'gif'}:
            ext = 'jpg' if candidate == 'jpeg' else candidate
    object_id = instance.pk if instance.pk else 'new'
    return f'{folder}/{prefix}_{object_id}.{ext}'


def validate_uploaded_image(uploaded):
    if not isinstance(uploaded, UploadedFile):
        return uploaded
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValidationError('Upload a JPG, PNG, WEBP, or GIF image.')
    if uploaded.size > MAX_IMAGE_BYTES:
        raise ValidationError('Image must be 5 MB or smaller.')
    return uploaded


def delete_replaced_cloudinary_image(public_id):
    """Remove a previous asset only when no service or combo still uses it."""
    if not public_id:
        return
    from bookings.models import ComboOffer, Service

    if Service.objects.filter(image=public_id).exists():
        return
    if ComboOffer.objects.filter(image=public_id).exists():
        return
    default_storage.delete(public_id)
