# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import hashlib
import mimetypes
import filetype


def get_file_mimetype(filepath):
    _, ext = os.path.splitext(filepath)
    kind = filetype.guess(filepath)
    if kind:
        mime = kind.mime
        ext = '.' + kind.extension
    else:
        try:
            mime = mimetypes.types_map.get(ext)
        except:
            mime = ext = None
    return (mime, ext)