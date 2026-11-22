import io
from unittest.mock import patch

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from bookings.models import Service


def tiny_png(name='cut.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class ServiceImageReplaceTests(TestCase):
    def fake_upload(self, content, **options):
        self.uploaded.append(options)
        return {'public_id': options['public_id']}

    def fake_destroy(self, public_id, **options):
        self.destroyed.append(public_id)
        return {'result': 'ok'}

    def setUp(self):
        self.uploaded = []
        self.destroyed = []
        self.upload_patch = patch('cloudinary.uploader.upload', side_effect=self.fake_upload)
        self.destroy_patch = patch('cloudinary.uploader.destroy', side_effect=self.fake_destroy)
        self.upload_patch.start()
        self.destroy_patch.start()

    def tearDown(self):
        self.upload_patch.stop()
        self.destroy_patch.stop()

    def test_reupload_overwrites_the_same_cloudinary_id(self):
        service = Service.objects.create(
            name='Haircut',
            price=Decimal('200.00'),
            duration_minutes=30,
            image=tiny_png('first.png'),
        )
        first_id = service.image.name
        self.assertTrue(first_id.endswith(f'service_{service.pk}'))
        self.assertEqual(len(self.uploaded), 1)
        self.assertTrue(self.uploaded[0]['overwrite'])
        self.assertTrue(self.uploaded[0]['invalidate'])
        self.assertFalse(self.destroyed)

        service.image = tiny_png('second.png')
        service.save()
        service.refresh_from_db()

        self.assertEqual(service.image.name, first_id)
        self.assertEqual(len(self.uploaded), 2)
        self.assertEqual(self.uploaded[1]['public_id'], self.uploaded[0]['public_id'])
        self.assertFalse(self.destroyed)

    def test_replacing_a_legacy_file_deletes_the_old_asset(self):
        service = Service.objects.create(
            name='Beard Trim',
            price=Decimal('150.00'),
            duration_minutes=20,
        )
        Service.objects.filter(pk=service.pk).update(image='media/services/legacy_photo')
        service.refresh_from_db()
        service.image = tiny_png('new.png')
        service.save()

        self.assertTrue(service.image.name.endswith(f'service_{service.pk}'))
        self.assertIn('media/services/legacy_photo', self.destroyed)

    def test_shared_legacy_file_is_kept_for_the_other_service(self):
        first = Service.objects.create(name='Cut', price=Decimal('200.00'), duration_minutes=30)
        second = Service.objects.create(name='Cut Plus', price=Decimal('300.00'), duration_minutes=45)
        Service.objects.filter(pk__in=[first.pk, second.pk]).update(image='media/services/shared')
        first.refresh_from_db()
        first.image = tiny_png('own.png')
        first.save()

        self.assertFalse(self.destroyed)
        second.refresh_from_db()
        self.assertEqual(second.image.name, 'media/services/shared')


class ServicePhotoUploadPageTests(TestCase):
    def setUp(self):
        self.upload_patch = patch(
            'cloudinary.uploader.upload',
            side_effect=lambda content, **options: {'public_id': options['public_id']},
        )
        self.destroy_patch = patch(
            'cloudinary.uploader.destroy',
            return_value={'result': 'ok'},
        )
        self.upload_patch.start()
        self.destroy_patch.start()
        user = get_user_model().objects.create_user(
            username='admin',
            password='test-pass-123',
            phone_number='9999999999',
            is_staff=True,
        )
        self.client.force_login(user)
        self.service = Service.objects.create(
            name='Hair Spa',
            price=Decimal('500.00'),
            duration_minutes=40,
        )

    def tearDown(self):
        self.upload_patch.stop()
        self.destroy_patch.stop()

    def test_services_page_offers_photo_upload_and_replaces_image(self):
        page = self.client.get('/admin/services/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Upload photo')
        self.assertContains(page, 'name="image"')

        response = self.client.post(
            '/admin/services/',
            {
                'action': 'upload_service_image',
                'service_id': self.service.pk,
                'next': '/admin/services/',
                'image': tiny_png(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertTrue(self.service.image.name.endswith(f'service_{self.service.pk}'))

        page = self.client.get('/admin/services/')
        self.assertContains(page, 'Replace photo')
