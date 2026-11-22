import os

import cloudinary.uploader
from cloudinary_storage.storage import MediaCloudinaryStorage


class OverwriteCloudinaryStorage(MediaCloudinaryStorage):
    """Upload each file to a fixed public id and replace the existing asset.

    Django Cloudinary's default storage keeps every upload as a new file.
    A stable public id with overwrite leaves one stored image per service.
    """

    def _upload(self, name, content):
        public_id, _ext = os.path.splitext(name)
        return cloudinary.uploader.upload(
            content,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            unique_filename=False,
            use_filename=False,
            resource_type=self._get_resource_type(name),
            tags=self.TAG,
        )
