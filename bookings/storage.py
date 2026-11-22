import os

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from django.core.cache import cache
from cloudinary_storage.storage import MediaCloudinaryStorage

VERSION_CACHE_TIMEOUT = 60 * 60 * 24 * 30


class OverwriteCloudinaryStorage(MediaCloudinaryStorage):
    """Upload each file to a fixed public id and replace the existing asset.

    Django Cloudinary's default storage keeps every upload as a new file and
    builds delivery URLs with a hard-coded /v1/ segment. That /v1/ URL is
    cached as immutable, so overwrites never show up. We overwrite in place
    and build URLs with Cloudinary's real asset version instead.
    """

    def _version_cache_key(self, public_id):
        return f'cloudinary_version:{public_id}'

    def _public_id_from_name(self, name):
        public_id, _ext = os.path.splitext(name)
        return public_id or name

    def _remember_version(self, public_id, version):
        if public_id and version is not None:
            cache.set(self._version_cache_key(public_id), str(version), VERSION_CACHE_TIMEOUT)

    def _lookup_version(self, public_id):
        key = self._version_cache_key(public_id)
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            info = cloudinary.api.resource(
                public_id,
                resource_type=self._get_resource_type(public_id),
            )
        except Exception:
            return None
        version = info.get('version')
        if version is not None:
            self._remember_version(public_id, version)
        return version

    def _upload(self, name, content):
        public_id = self._public_id_from_name(name)
        response = cloudinary.uploader.upload(
            content,
            public_id=public_id,
            asset_folder=os.path.dirname(public_id),
            overwrite=True,
            invalidate=True,
            unique_filename=False,
            use_filename=False,
            resource_type=self._get_resource_type(name),
            tags=self.TAG,
        )
        self._remember_version(response.get('public_id') or public_id, response.get('version'))
        return response

    def _get_url(self, name):
        name = self._prepend_prefix(name)
        public_id = self._public_id_from_name(name)
        version = self._lookup_version(public_id)
        options = {
            'resource_type': self._get_resource_type(name),
            'secure': True,
        }
        if version:
            options['version'] = version
        else:
            # Avoid Cloudinary's default /v1/ URLs, which stay cached forever.
            options['force_version'] = False
        url, _options = cloudinary.utils.cloudinary_url(public_id, **options)
        return url
