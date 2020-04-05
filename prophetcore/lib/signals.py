# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.apps import apps
from django.dispatch import receiver
from django.db.models import signals
from prophetcore.lib.utils import get_content_type_for_model, fields_for_model
from prophetcore.models import User, Configure


@receiver(signals.post_save, sender=User, dispatch_uid='initial_user_config')
def initial_user_config(instance, created, **kwargs):
    if created:
        models = apps.get_app_config('prophetcore').get_models()
        exclude = ['onidc', 'deleted', 'mark']
        configures = []
        for model in models:
            fds = [f for f in fields_for_model(model) if f not in exclude]
            _fields = getattr(model._meta, 'list_display', fds)
            fields = _fields if isinstance(_fields, list) else fds
            content = {'list_only_date': 1, 'list_display': fields}
            config = dict(
                onidc=instance.onidc,
                creator=instance,
                mark='list',
                content_type=get_content_type_for_model(model),
                content=json.dumps(content),
            )
            configures.append(Configure(**config))
        Configure.objects.bulk_create(configures)