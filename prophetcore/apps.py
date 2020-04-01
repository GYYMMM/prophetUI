# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.apps import AppConfig


class prophetcoreConfig(AppConfig):
    name = 'prophetcore'
    verbose_name = "数据中心运维"

    def ready(self):
        from prophetcore.lib import signals
