#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 20-4-5 下午1:30
# @Author  : cherry_wb
# @Site    : 
# @File    : myfilter.py
# @Software: PyCharm
from django import template
from django.template.defaultfilters import stringfilter
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe, SafeData
from django.utils.safestring import mark_safe
from django.utils.text import normalize_newlines
from django.utils.html import escape
import re

register = template.Library()

@register.filter(name='spacify', is_safe=True)
def spacify(value, autoescape=None):
    autoescape = autoescape and not isinstance(value, SafeData)
    value = normalize_newlines(value)
    if autoescape:
        value = escape(value)
    value = mark_safe(value.replace('  ', ' &nbsp;'))
    return mark_safe(value.replace('\n', '<br />'))

spacify.needs_autoescape = True