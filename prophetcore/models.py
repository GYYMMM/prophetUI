# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import uuid

from django.db import models
from django.db.models.fields import BLANK_CHOICE_DASH
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import (
    GenericForeignKey, GenericRelation
)

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import formats, timezone
from django.utils.encoding import force_text
from six import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import logger

try:
    from django.core.urlresolvers import reverse_lazy
except:
    from django.urls import reverse_lazy

from django.db.models import options

# Create your models here.
from prophetcore.lib.models.utils import get_file_mimetype


def upload_to(instance, filename):
    ext = filename.split('.')[-1]
    new_filename = "%s" % uuid.uuid4()
    today = timezone.datetime.now().strftime(r'%Y/%m/%d')
    return os.path.join('uploads', today, new_filename, filename)


EXT_NAMES = (
    'level', 'hidden', 'dashboard', 'metric', 'icon',
    'icon_color', 'default_filters', 'list_display', 'extra_fields'
)

models.options.DEFAULT_NAMES += EXT_NAMES

COLOR_MAPS = (
    ("red", "红色"),
    ("orange", "橙色"),
    ("yellow", "黄色"),
    ("green", "深绿色"),
    ("blue", "蓝色"),
    ("muted", "灰色"),
    ("black", "黑色"),
    ("aqua", "浅绿色"),
    ("gray", "浅灰色"),
    ("navy", "海军蓝"),
    ("teal", "水鸭色"),
    ("olive", "橄榄绿"),
    ("lime", "高亮绿"),
    ("fuchsia", "紫红色"),
    ("purple", "紫色"),
    ("maroon", "褐红色"),
    ("white", "白色"),
    ("light-blue", "暗蓝色"),
)


class Mark(models.Model):
    CHOICES = (
        ('shared', "已共享的"),
        ('pre_share', "预共享的"),
    )
    mark = models.CharField(
        max_length=64, choices=CHOICES,
        blank=True, null=True,
        verbose_name="系统标记", help_text="系统Slug内容标记")

    class Meta:
        level = 0
        hidden = False
        dashboard = False
        metric = ""
        icon = 'fa fa-circle-o'
        icon_color = ''
        default_filters = {'deleted': False}
        list_display = '__all__'
        extra_fields = []
        abstract = True

    @cached_property
    def get_absolute_url(self):
        opts = self._meta
        # if opts.proxy:
        #    opts = opts.concrete_model._meta
        url = reverse_lazy('prophetcore:detail', args=[opts.model_name, self.pk])
        return url

    @cached_property
    def get_edit_url(self):
        opts = self._meta
        url = reverse_lazy('prophetcore:update', args=[opts.model_name, self.pk])
        return url

    def title_description(self):
        return self.__str__()


class Creator(models.Model):
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_creator",
        verbose_name="创建人", help_text="该对象的创建人")

    class Meta:
        abstract = True


class Operator(models.Model):
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_operator",
        blank=True, null=True,
        verbose_name="修改人", help_text="该对象的修改人"
    )

    class Meta:
        abstract = True


class Created(models.Model):
    created = models.DateTimeField(
        default=timezone.datetime.now, editable=True,
        verbose_name="创建日期", help_text="该对象的创建日期"
    )

    class Meta:
        abstract = True


class Modified(models.Model):
    modified = models.DateTimeField(
        auto_now=True, verbose_name="修改日期",
        help_text="该对象的修改日期"
    )

    class Meta:
        abstract = True
        ordering = ['-modified']


class Actived(models.Model):
    actived = models.NullBooleanField(
        default=True, verbose_name="已启用",
        help_text="该对象是否为有效资源"
    )

    class Meta:
        abstract = True


class Deleted(models.Model):
    deleted = models.NullBooleanField(
        default=False, editable=False,
        verbose_name="已删除", help_text="该对象是否已被删除"
    )

    class Meta:
        abstract = True


class Parent(models.Model):
    parent = models.ForeignKey(
        'self',
        blank=True, null=True, on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_parent",
        verbose_name="父级对象", help_text="该对象的上一级关联对象"
    )

    class Meta:
        abstract = True


class Onidc(models.Model):
    onidc = models.ForeignKey(
        'Idc',
        blank=True, null=True, on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_onidc",
        verbose_name="所属节点", help_text="该资源所属的节点"
    )

    class Meta:
        abstract = True


class Tag(models.Model):
    tags = models.ManyToManyField(
        'Option',
        blank=True, limit_choices_to={'flag__icontains': 'tags'},
        related_name="%(app_label)s_%(class)s_tags",
        verbose_name="通用标签",
        help_text="可拥有多个标签,字段数据来自节点选项"
    )

    class Meta:
        abstract = True


class Intervaltime(models.Model):
    start_time = models.DateTimeField(
        default=timezone.datetime.now, editable=True,
        verbose_name="开始时间", help_text="该对象限定的开始时间"
    )
    end_time = models.DateTimeField(
        default=timezone.datetime.now, editable=True,
        null=True, blank=True,
        verbose_name="结束时间", help_text="该对象限定的结束时间"
    )

    class Meta:
        abstract = True


class PersonTime(Creator, Created, Operator, Modified):
    class Meta:
        abstract = True


class ActiveDelete(Actived, Deleted):
    class Meta:
        abstract = True


class Contentable(Onidc, Mark, PersonTime, ActiveDelete):
    content_type = models.ForeignKey(
        ContentType,
        models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_('content type'),
        related_name="%(app_label)s_%(class)s_content_type",
        limit_choices_to={'app_label': 'prophetcore'}
    )
    object_id = models.PositiveIntegerField(
        _('object id'), blank=True, null=True)
    object_repr = GenericForeignKey('content_type', 'object_id')
    content = models.TextField(verbose_name="详细内容", blank=True)

    def __str__(self):
        return force_text(self.object_repr)

    class Meta:
        abstract = True


class Comment(Contentable):
    class Meta(Mark.Meta):
        level = 2
        list_display = [
            'creator', 'created', 'modified', 'content'
        ]
        hidden = getattr(settings, 'HIDDEN_COMMENT_NAVBAR', True)
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "备注信息"


class Configure(Contentable):
    class Meta(Mark.Meta):
        hidden = True
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "用户配置"

    def __str__(self):
        return "{}-{} : {}".format(self.creator, self.content_type, self.pk)


class Remark(models.Model):
    comment = GenericRelation(
        'Comment',
        related_name="%(app_label)s_%(class)s_comment",
        verbose_name="备注信息")

    @property
    def remarks(self):
        return self.comment.filter(deleted=False, actived=True)

    class Meta:
        abstract = True


class Syslog(Contentable):
    action_flag = models.CharField(_('action flag'), max_length=32)
    message = models.TextField(_('change message'), blank=True)
    object_desc = models.CharField(
        max_length=128,
        verbose_name="对象描述"
    )
    related_client = models.CharField(
        max_length=128,
        blank=True, null=True,
        verbose_name="关系客户"
    )

    def title_description(self):
        time = formats.localize(timezone.template_localtime(self.created))
        text = '{} > {} > {}了 > {}'.format(
            time, self.creator, self.action_flag, self.content_type
        )
        return text

    class Meta(Mark.Meta):
        level = 1
        icon = 'fa fa-history'
        list_display = [
            'created', 'creator', 'action_flag', 'content_type',
            'object_desc', 'related_client', 'message', 'actived',
        ]
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        ordering = ['-created', ]
        verbose_name = verbose_name_plural = _('log entries')


@python_2_unicode_compatible
class User(AbstractUser, Onidc, Mark, ActiveDelete, Remark):
    slaveidc = models.ManyToManyField(
        'Idc',
        blank=True,
        verbose_name="附属节点",
        related_name="%(app_label)s_%(class)s_slaveidc"
    )
    upper = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        verbose_name="直属上级",
        related_name="%(app_label)s_%(class)s_upper"
    )
    mobile = models.CharField(max_length=16, blank=True, verbose_name="手机号码")
    avatar = models.ImageField(
        upload_to='avatar/%Y/%m/%d',
        default="avatar/default.png",
        verbose_name="头像"
    )
    settings = models.TextField(
        blank=True,
        verbose_name=_("settings"),
        help_text=_("user settings use json format")
    )

    def __str__(self):
        return self.first_name or self.username

    def title_description(self):
        text = '{} > {} '.format(
            self.onidc, self.__str__()
        )
        return text

    class Meta(AbstractUser.Meta, Mark.Meta):
        level = 2
        icon = 'fa fa-user'
        icon_color = 'aqua'
        metric = "个"
        dashboard = True
        list_display = [
            'username', 'first_name', 'email', 'onidc',
            'mobile', 'last_login', 'is_superuser',
            'is_staff', 'is_active'
        ]
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "用户信息"


@python_2_unicode_compatible
class Idc(Mark, PersonTime, ActiveDelete, Remark):
    name = models.CharField(
        max_length=16,
        unique=True,
        verbose_name="先知节点简称",
        help_text="先知节点简称,尽量简洁。例如：XA01"
    )
    desc = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="先知节点全称",
        help_text="请填写定义的先知节点全称。例如：xxx机房"
    )
    codename = models.SlugField(
        blank=True, null=True,
        verbose_name="先知节点代码",
        help_text=_("先知节点代码，用于编号前缀")
    )
    emailgroup = models.EmailField(
        max_length=32, blank=True, null=True,
        verbose_name="邮箱组",
        help_text="该先知节点的邮箱组"
    )
    address = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="先知节点地址",
        help_text="先知节点的具体地址"
    )
    duty = models.CharField(
        max_length=16,
        blank=True, null=True,
        default="7*24",
        verbose_name="值班类型",
        help_text="先知节点值班类型,例如:5*8"
    )
    tel = models.CharField(
        max_length=32,
        verbose_name="值班电话",
        help_text="联系方式，例如：13800138000"
    )
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name="管理人员",
        help_text="权限将比普通用户多一些"
    )
    settings = models.TextField(
        blank=True,
        verbose_name=_("settings"),
        help_text=_("data center extended settings use json format")
    )

    def __str__(self):
        return self.name

    class Meta(Mark.Meta):
        level = 2
        # icon = 'fa fa-server'
        # metric = "个"
        # dashboard = True
        list_display = [
            'name', 'desc', 'emailgroup', 'address',
            'duty', 'tel'
        ]
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "先知节点"


@python_2_unicode_compatible
class Option(
    Onidc, Parent, Mark, PersonTime, ActiveDelete, Remark
):
    """ mark in "`shared`, `system`, `_tpl`" """
    flag = models.SlugField(
        max_length=64,
        choices=BLANK_CHOICE_DASH,
        verbose_name="标记类型",
        help_text="该对象的标记类型,比如：目标类型")
    text = models.CharField(
        max_length=64,
        verbose_name="显示内容",
        help_text="记录内容,模板中显示的内容")
    description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="记录说明",
        help_text="记录内容的帮助信息/说明/注释")
    color = models.SlugField(
        max_length=12,
        choices=COLOR_MAPS,
        null=True, blank=True,
        verbose_name="颜色",
        help_text="该标签使用的颜色, 用于报表统计以及页面区分")
    master = models.NullBooleanField(
        default=False,
        verbose_name="默认使用",
        help_text="用于默认选中,比如:默认使用的设备类型是 服务器")

    def __init__(self, *args, **kwargs):
        super(Option, self).__init__(*args, **kwargs)
        flag = self._meta.get_field('flag')
        flag.choices = self.choices_to_field()

    @classmethod
    def choices_to_field(cls):
        _choices = [BLANK_CHOICE_DASH[0], ]
        for rel in cls._meta.related_objects:
            object_name = rel.related_model._meta.object_name.capitalize()
            field_name = rel.remote_field.name.capitalize()
            name = "{}-{}".format(object_name, field_name)
            remote_model_name = rel.related_model._meta.verbose_name
            verbose_name = "{}-{}".format(
                remote_model_name, rel.remote_field.verbose_name
            )
            _choices.append((name, verbose_name))
        return sorted(_choices)

    @property
    def flag_to_dict(self):
        maps = {}
        for item in self.choices_to_field():
            maps[item[0]] = item[1]
        return maps

    def clean_fields(self, exclude=None):
        super(Option, self).clean_fields(exclude=exclude)
        if not self.pk:
            verify = self._meta.model.objects.filter(
                onidc=self.onidc, master=self.master, flag=self.flag)
            if self.master and verify.exists():
                raise ValidationError({
                    'text': "标记类型: {} ,已经存在一个默认使用的标签: {}"
                            " ({}).".format(self.flag_to_dict.get(self.flag),
                                            self.text, self.description)})

    def __str__(self):
        return self.text

    def title_description(self):
        text = '{} > {}'.format(self.get_flag_display(), self.text)
        return text

    def save(self, *args, **kwargs):
        shared_flag = ['clientkf', 'clientsales', 'goodsbrand', 'goodsunit']
        if self.flag in shared_flag:
            self.mark = 'shared'
        return super(Option, self).save(*args, **kwargs)

    class Meta(Mark.Meta):
        level = 1
        icon = 'fa fa-cogs'
        metric = "项"
        list_display = [
            'text', 'flag', 'description', 'master',
            'color', 'parent', 'actived', 'onidc', 'mark'
        ]
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        ordering = ['-actived', '-modified']
        unique_together = (('flag', 'text'),)
        verbose_name = verbose_name_plural = "节点选项"

@python_2_unicode_compatible
class Document(Onidc, Mark, PersonTime, ActiveDelete, Remark):
    title = models.CharField(max_length=128, verbose_name="文档标题")
    body = models.TextField(verbose_name="文档内容")
    category = models.ForeignKey(
        'Option',
        on_delete=models.SET_NULL,
        blank=True, null=True,
        limit_choices_to={'flag': 'Document-Category'},
        related_name="%(app_label)s_%(class)s_category",
        verbose_name="文档分类",
        help_text="分类, 从选项中选取")
    status = models.ForeignKey(
        'Option',
        on_delete=models.SET_NULL,
        blank=True, null=True,
        limit_choices_to={'flag': 'Document-Status'},
        related_name="%(app_label)s_%(class)s_status",
        verbose_name="文档状态",
        help_text="从选项中选取")
    tags = models.ManyToManyField(
        'Option',
        blank=True, limit_choices_to={'flag': 'Document-Tags'},
        related_name="%(app_label)s_%(class)s_tags",
        verbose_name="通用标签",
        help_text="可拥有多个标签,字段数据来自选项"
    )

    def __str__(self):
        return self.title

    class Meta(Mark.Meta):
        level = 1
        icon = 'fa fa-book'
        icon_color = 'green'
        metric = "份"
        dashboard = True
        list_display = [
            'title',
            'category',
            'created',
            'creator',
            'status',
            'onidc',
            'tags']
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "文档资料"


@python_2_unicode_compatible
class Attachment(Onidc, Mark, PersonTime, ActiveDelete, Tag, Remark):
    name = models.CharField(
        max_length=255,
        verbose_name=_("file name")
    )
    file = models.FileField(
        upload_to=upload_to,
        verbose_name=_("file")
    )

    def __str__(self):
        return self.name

    @property
    def mimetype(self):
        return get_file_mimetype(self.file.path)

    class Meta(Mark.Meta):
        level = 1
        icon = 'fa fa-file'
        metric = "份"
        hidden = True
        list_display = [
            'name',
            'file',
            'created',
            'creator',
            'onidc',
            'tags']
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        verbose_name = verbose_name_plural = "媒体文件"


@python_2_unicode_compatible
class Target(Onidc, Mark, PersonTime, ActiveDelete, Remark):

    name = models.CharField(
        max_length=32,
        verbose_name="测试名称", help_text="比如: lava-who")
    binary = models.CharField(
        max_length=256,
        blank=True, default="/home/prophet/binary001",
        verbose_name="文件路径",
        help_text="比如: /path/to/test/target/")
    _INPUT_TYPE = (
        ('file', "文件输入"),
        ('stdin', "标准输入"),
        ('argv', "命令行输入"),
        ('net', "网络输入"),
    )
    inputtype = models.SlugField(
        choices=_INPUT_TYPE, default='file',
        verbose_name="输入类型", help_text="默认为文件输入")

    cmdargs = models.CharField(
        max_length=256,
        blank=True, null=True, default="",
        verbose_name="Fuzzing参数",
        help_text="比如: -qiling -triton -p 2 -cp 1")

    targetargs = models.CharField(
        max_length=256,
        blank=True, null=True, default="",
        verbose_name="目标参数",
        help_text="比如: -d @@")

    runningpid = models.CharField(
        max_length=32,
        blank=True, null=True,
        verbose_name="进程ID", help_text="比如: 2706")

    tags = models.ManyToManyField(
        'Option',
        blank=True, limit_choices_to={'flag': 'Target-Tags'},
        related_name="%(app_label)s_%(class)s_tags",
        verbose_name="测试对象标签",
        help_text="可拥有多个标签,字段数据来自机房选项"
    )

    def __str__(self):
        return self.name

    def title_description(self):
        text = '{} > {} > {}'.format(
            self.name, self.inputtype, self.tags
        )
        return text

    class Meta(Mark.Meta):
        level = 0
        # extra_fields = ['list_units']
        icon = 'fa fa-file-code-o'
        icon_color = 'blue'
        metric = "个"
        dashboard = True
        list_display = [
            'name', 'binary', 'inputtype', 'actived', 'modified'
        ]
        default_permissions = ('view', 'add', 'change', 'delete', 'exports')
        ordering = ['-modified']
        unique_together = (('onidc', 'name',),)
        verbose_name = verbose_name_plural = "测试对象"
