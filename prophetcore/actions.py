# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import copy
import json
import time
import os,stat
import zipfile
import shutil
import tempfile
from functools import wraps

import subprocess,psutil
import signal
from django.contrib import admin
from django.conf import settings
from io import BytesIO

from django.contrib.admin.utils import get_deleted_objects

from django.core.exceptions import PermissionDenied
from wsgiref.util import FileWrapper
from django.db import router
from django.db.models import Sum
from django.template.response import TemplateResponse
from django.utils import timezone
from django.http import HttpResponse, FileResponse
from django.utils.encoding import force_text
from django.forms.models import model_to_dict
from notifications.signals import notify as notify_user

from prophetcore.lib.tasks import log_action
from prophetcore.lib.utils import (
    diff_dict, get_content_type_for_model, shared_queryset, SpooledFile
)
from prophetcore.mixins import system_menus
from prophetcore.exports import make_to_excel
from prophetcore.models import Comment, Target, Option



SOFT_DELELE = getattr(settings, 'SOFT_DELELE', False)

general = ['download', 'actived', 'reactive', ]
user = idc = ['download']
target = ['downloadfuzzingresult', 'startfuzzing','stopfuzzing', 'getfuzzingstatus' ,'delete']
syslog = ['download', 'actived']
comment = ['download', 'actived', 'delete']


def check_multiple_clients(func):
    @wraps(func)
    def wrapper(request, queryset):
        model = queryset.model
        opts = model._meta
        if hasattr(model, 'client'):
            verify = queryset.values('client').order_by('client').distinct()
            if verify.count() > 1:
                mesg = "不允许操作多个不同客户的 {}".format(opts.verbose_name)
                return mesg
        return func(request, queryset)
    return wrapper


def construct_model_meta(request, model, title=None):
    opts = model._meta
    meta = {}
    if title is None:
        title = ''
    meta['logo'] = request.user.onidc
    meta['title'] = "{} {}".format(title, opts.verbose_name)
    meta['icon'] = opts.icon
    meta['model_name'] = opts.model_name
    meta['verbose_name'] = opts.verbose_name
    return meta, system_menus


def construct_context(request, queryset, action, action_name):
    meta, menus = construct_model_meta(request, queryset.model, action_name)
    context = dict(
        meta=meta,
        menus=menus,
        action=action,
        action_name=action_name,
        queryset=queryset,
    )
    return context


def download(request, queryset):
    return make_to_excel(queryset)


download.description = "导出"
download.icon = 'fa fa-download'
download.required = 'exports'


def downloadfuzzingresult(request, queryset):
    #output = tempfile.NamedTemporaryFile(delete=False) #TemporaryFile()
    #tempfile.SpooledTemporaryFile
    output = BytesIO()
    zipf = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)

    for obj in queryset:
        src_dir = os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name)
        pre_len = len(os.path.dirname(src_dir))
        for parent, dirnames, filenames in os.walk(src_dir):
            for filename in filenames:
                pathfile = os.path.join(parent, filename)
                arcname = pathfile[pre_len:].strip(os.path.sep)  # 相对路径
                zipf.write(pathfile, arcname)
        break
    #zipf.setpassword(b"prophet")
    zipf.close()
    output.seek(0)
    response = HttpResponse(output)
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = 'attachment;filename="{}.tar.gz"'.format(obj.name)
    return response
    # output.close()
    # file = open(output.name, 'rb')
    # response = FileResponse(file)
    # response['Content-Type'] = 'application/octet-stream'
    # response['Content-Disposition'] = 'attachment;filename="{}.tar.gz"'.format(obj.name)
    # return response

downloadfuzzingresult.description = "导出"
downloadfuzzingresult.icon = 'fa fa-download'
downloadfuzzingresult.required = 'exports'


def run_sh(cmd, **kwargs):
    print("Executing: %s" % ' '.join(cmd))
    return subprocess.Popen(cmd, **kwargs)


@check_multiple_clients
def startfuzzing(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "开始"
    if not os.path.exists(settings.WORKING_ROOT):
        try:
            os.mkdir(settings.WORKING_ROOT)
            os.mkdir(os.path.join(settings.WORKING_ROOT, "fuzzer_in"))
            os.mkdir(os.path.join(settings.WORKING_ROOT, "fuzzer_out"))
        except:
            pass
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = True
            b_path = os.path.join(settings.BASE_DIR, obj.binary[1:])
            os.chmod(b_path,stat.S_IXUSR |stat.S_IRUSR |stat.S_IWUSR | stat.S_IWGRP | stat.S_IRGRP | stat.S_IXOTH | stat.S_IROTH | stat.S_IWOTH)
            cmd = [sys.executable, os.path.join(settings.BASE_DIR, "workingFuzzer.py"),
                   os.path.join(settings.WORKING_ROOT, "fuzzer_in"),
                   os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name)]
            cmd += obj.cmdargs.split(" ")
            cmd += [b_path, "--", obj.targetargs]
            if not os.path.exists(os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name)):
                try:
                    os.mkdir(os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name))
                except:
                    pass
            #file_output = open(os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name, "ui.log"), "w")
            file_output = SpooledFile(os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name, "ui.log"), mode="w", max_size=100*1024)
            p = run_sh(cmd,stdin=subprocess.PIPE, stdout=file_output, stderr=subprocess.PIPE, cwd=settings.BASE_DIR)
            obj.runningpid = p.pid

            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag="开始",
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )

        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


startfuzzing.description = "开始"
startfuzzing.icon = 'fa fa-check-circle-o'

def kill_all_process(pid):
    proc = psutil.Process(pid)
    procs = proc.children(recursive=True)
    procs.append(proc)
    for proc in procs:
        try:
            proc.send_signal(signal.SIGINT)
            time.sleep(2)
        except:
            pass
    for proc in procs:
        try:
            proc.terminate()
        except:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=1)
    for p in alive:
        try:
            p.kill()
        except:
            pass

@check_multiple_clients
def stopfuzzing(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "停止"
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            try:
                #os.kill(int(obj.runningpid), signal.SIGKILL)
                obj.actived = False
                kill_all_process(int(obj.runningpid))
                obj.runningpid = ""
            except Exception as e:
                print(e)

            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag="停止",
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


stopfuzzing.description = "停止"
stopfuzzing.icon = 'fa fa-ban'


@check_multiple_clients
def getfuzzingstatus(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "进度"
    for obj in queryset:
        p = subprocess.Popen('tail ' + os.path.join(settings.WORKING_ROOT, "fuzzer_out", obj.name, "ui.log") +' -n 40 | ./ansi2html.sh --bg=dark --body-only --palette=tango', shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout, stderr = p.communicate()
        _extra = dict(
            content=stdout.decode(),
            fuzzingname = obj.name
        )
        break
    context = construct_context(request, queryset, action, action_name)
    context.update(_extra)
    return TemplateResponse(request, 'base/base_fuzzingstatus.html', context)


getfuzzingstatus.description = "进度"
getfuzzingstatus.icon = 'fa fa-spinner fa-spin'

@check_multiple_clients
def html_print(request, queryset):
    model = queryset.model
    opts = model._meta
    action = sys._getframe().f_code.co_name
    action_name = "打印"
    verify = queryset.values('status').order_by('status').distinct()
    if verify.count() > 1:
        mesg = "不允许打印多个不同状态的 {}".format(opts.verbose_name)
        return mesg
    extra_for = queryset.count() - 10 < 0
    if extra_for:
        extra_for = list(range(abs(queryset.count() - 10)))
    _extra = dict(
        extra_for=extra_for,
        ticket=int(time.time()),
    )
    context = construct_context(request, queryset, action, action_name)
    context.update(_extra)
    templates = ["%s/print.html" % (opts.model_name), "base/print.html"]
    return TemplateResponse(request, templates, context)


html_print.description = "打印"
html_print.icon = 'fa fa-print'
download.required = 'view'


@check_multiple_clients
def actived(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "停用"
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = False
            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag="停用",
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


actived.description = "停用"
actived.icon = 'fa fa-ban'


@check_multiple_clients
def reclaim(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "回收"
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = False
            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag=action_name,
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


reclaim.description = "回收"
reclaim.icon = 'fa fa-ban'


@check_multiple_clients
def cancel_reclaim(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "取消回收"
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = True
            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag=action_name,
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


cancel_reclaim.description = "取消回收"
cancel_reclaim.icon = 'fa fa-check-circle-o'


@check_multiple_clients
def reactive(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "启用"
    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = True
            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag=action_name,
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


reactive.description = "启用"
reactive.icon = 'fa fa-check-circle-o'


@check_multiple_clients
def outbound(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "出库"
    queryset = queryset.filter(actived=True)
    if not queryset.exists():
        return "选择无结果"

    total = queryset.aggregate(Sum('amount'))
    if request.POST.get('post') and request.POST.getlist('items'):
        def construct_item(index):
            obj = queryset.get(pk=int(index))
            out_amount = int(request.POST.get('count-' + str(index)))
            out_serials = request.POST.getlist('sn-' + str(index))
            copy_needed = True
            if int(out_amount) == obj.amount:
                copy_needed = False
            comment = request.POST.get(('comment-' + index), None)
            return obj, copy_needed, out_serials, out_amount, comment

        for item in request.POST.getlist('items'):
            obj, _copy, out_serials, out_amount, comment = construct_item(item)
            o = copy.deepcopy(obj)
            if _copy:
                hold = [s for s in obj.serials.split(
                    ',') if s not in out_serials]
                obj.amount -= out_amount
                obj.serials = ','.join(hold)
                new_obj = copy.deepcopy(obj)
                new_obj.pk = None
                new_obj.amount = out_amount
                new_obj.serials = ','.join(out_serials)
                new_obj.actived = False
                new_obj.creator = request.user
                new_obj.created = timezone.datetime.now()
                new_obj.operator = None
                new_obj.parent = obj
                new_obj.save()
                comment_obj = new_obj
            else:
                obj.actived = False
                obj.operator = request.user
                comment_obj = obj
            obj.save()
            if comment:
                Comment.objects.create(
                    object_repr=comment_obj, content=comment,
                    creator=request.user, onidc=obj.onidc)
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=comment_obj.pk,
                action_flag=action_name,
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None
    context = construct_context(request, queryset, action, action_name)
    _extra = dict(total=total)
    context.update(_extra)
    return TemplateResponse(request, 'base/items_out.html', context)


outbound.description = "出库"
outbound.icon = 'fa fa-check'


@check_multiple_clients
def reoutbound(request, queryset):
    action = sys._getframe().f_code.co_name
    action_name = "取消出库"
    queryset = queryset.filter(actived=False)
    if not queryset.exists():
        return "查无结果"

    if request.POST.get('post'):
        for obj in queryset:
            o = copy.deepcopy(obj)
            obj.actived = True
            obj.save()
            diffs = diff_dict(model_to_dict(o), model_to_dict(obj))
            log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(obj, True).pk,
                object_id=obj.pk,
                action_flag=action_name,
                message=json.dumps(list(diffs.keys())),
                content=json.dumps(diffs)
            )
        return None

    context = construct_context(request, queryset, action, action_name)
    return TemplateResponse(request, 'base/base_confirmation.html', context)


reoutbound.description = "取消出库"
reoutbound.icon = 'fa fa-undo'


def delete(request, queryset):
    model = queryset.model
    opts = model._meta
    action = sys._getframe().f_code.co_name
    action_name = "删除"

    modeladmin = admin.site._registry.get(model)
    # queryset = queryset.filter(actived=False)
    if not modeladmin.has_delete_permission(request):
        raise PermissionDenied
    using = router.db_for_write(modeladmin.model)

    deletable_objects, model_count, perms_needed, protected = get_deleted_objects(
        queryset, request, modeladmin.admin_site)

    if request.POST.get('post') and not protected:
        if perms_needed:
            raise PermissionDenied
        if queryset.count():
            for obj in queryset:
                log_action(
                    user_id=request.user.pk,
                    content_type_id=get_content_type_for_model(obj, True).pk,
                    object_id=obj.pk,
                    action_flag="删除"
                )
            if not SOFT_DELELE:
                queryset.delete()
            else:
                queryset.update(deleted=True, actived=False)
        return None

    if len(queryset) == 1:
        objects_name = force_text(opts.verbose_name)
    else:
        objects_name = force_text(opts.verbose_name_plural)

    meta, menus = construct_model_meta(request, model, action_name)

    context = dict(
        objects_name=objects_name,
        deletable_objects=[deletable_objects],
        model_count=dict(model_count).items(),
        queryset=queryset,
        perms_lacking=perms_needed,
        protected=protected,
        opts=opts,
        meta=meta,
        action=action,
        action_name=action_name,
        menus=menus,
    )

    request.current_app = modeladmin.admin_site.name

    return TemplateResponse(request, 'base/base_confirmation.html', context)


delete.description = "删除"
delete.icon = 'fa fa-trash'
delete.required = 'delete'
