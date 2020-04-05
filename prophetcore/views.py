# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

# Create your views here.
from django.apps import apps
from django.shortcuts import render
from django.views.generic import View, TemplateView
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordResetView,
    PasswordResetDoneView, PasswordResetConfirmView,
    PasswordResetCompleteView, PasswordChangeDoneView,
    PasswordChangeView
)
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from django.utils.encoding import force_text
from django.utils.functional import cached_property

try:
    from django.core.urlresolvers import reverse_lazy
except:
    from django.urls import reverse_lazy

from prophetcore.lib.utils import shared_queryset
from prophetcore.mixins import BaseRequiredMixin
from prophetcore.models import (
    Option, Target,  Syslog, ContentType,)

login = LoginView.as_view(template_name='accounts/login.html')

logout = LogoutView.as_view(template_name='accounts/logout.html')

password_reset = PasswordResetView.as_view(
    template_name='accounts/password_reset_form.html',
    email_template_name='accounts/password_reset_email.html',
    subject_template_name='accounts/password_reset_subject.txt',
)

password_reset_done = PasswordResetDoneView.as_view(
    template_name='accounts/password_reset_done.html'
)

reset = PasswordResetConfirmView.as_view(
    template_name='accounts/password_reset_confirm.html'
)

reset_done = PasswordResetCompleteView.as_view(
    template_name='accounts/password_reset_complete.html'
)


class PasswordChangeView(BaseRequiredMixin, PasswordChangeView):
    template_name = 'accounts/password_change_form.html'
    success_url = reverse_lazy('prophetcore:index')


password_change = PasswordChangeView.as_view()

password_change_done = PasswordChangeDoneView.as_view(
    template_name='accounts/password_change_done.html'
)


class SummernoteUploadAttachment(BaseRequiredMixin, View):
    def __init__(self):
        super(SummernoteUploadAttachment, self).__init__()

    def get(self, request, *args, **kwargs):
        return JsonResponse({
            'status': 'false',
            'message': _('Only POST method is allowed'),
        }, status=400)

    def post(self, request, *args, **kwargs):
        if not request.FILES.getlist('files'):
            return JsonResponse({
                'status': 'false',
                'message': _('No files were requested'),
            }, status=400)

        # remove unnecessary CSRF token, if found
        kwargs = request.POST.copy()
        kwargs.pop("csrfmiddlewaretoken", None)

        try:
            attachments = []

            for file in request.FILES.getlist('files'):

                # create instance of appropriate attachment class
                from prophetcore.models import Attachment
                attachment = Attachment()

                attachment.onidc = request.user.onidc
                attachment.creator = request.user
                attachment.file = file
                attachment.name = file.name

                if file.size > 1024 * 1024 * 10:
                    return JsonResponse({
                        'status': 'false',
                        'message': _('File size exceeds the limit allowed and cannot be saved'),
                    }, status=400)

                # calling save method with attachment parameters as kwargs
                attachment.save(**kwargs)
                attachments.append(attachment)

            return HttpResponse(render_to_string('document/upload_attachment.json', {
                'attachments': attachments,
            }), content_type='application/json')
        except IOError:
            return JsonResponse({
                'status': 'false',
                'message': _('Failed to save attachment'),
            }, status=500)


class IndexView(BaseRequiredMixin, TemplateView):

    template_name = 'index.html'

    def make_years(self, queryset):
        years = queryset.datetimes('created', 'month')
        if years.count() > 12:
            ranges = years[(years.count()-12):years.count()]
        else:
            ranges = years[:12]
        return ranges

    def make_running_statistics(self):
        data = []
        dobjects = Target.objects.filter(onidc_id=self.onidc_id)
        keys = Option.objects.filter(flag__in=['Target-Tags'])
        keys = shared_queryset(keys, self.onidc_id)
        for k in keys:
            d = []
            c = dobjects.filter(tags__in=[k],deleted = 0).count()
            if c > 0:
                d.append(force_text(k))
                d.append(c)
            if d:
                data.append(d)
        return data

    def make_actived_statistics(self):
        data = []
        dobjects = Target.objects.filter(onidc_id=self.onidc_id)
        for k in range(2):
            d = []
            c = dobjects.filter(actived = k,deleted = 0).count()
            if k == 1:
                d.append("已启动")
            else:
                d.append("未启动")
            d.append(c)
            data.append(d)
        return data

    def make_state_items(self):
        state_items = [
            {
                'model_name': app._meta.model_name,
                'verbose_name': app._meta.verbose_name,
                'icon': app._meta.icon,
                'icon_color': 'bg-' + app._meta.icon_color,
                'level': app._meta.level,
                'metric': app._meta.metric,
                'count': app.objects.filter(
                    onidc=self.request.user.onidc).filter(
                    **app._meta.default_filters).count(),
            } for app in apps.get_app_config('prophetcore').get_models() if getattr(
                app._meta,
                'dashboard')]
        return state_items

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        context['state_items'] = self.make_state_items()
        context['running_statistics'] = self.make_running_statistics()
        context['actived_statistics'] = self.make_actived_statistics()
        return context


class ProfileView(BaseRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    # def get(self, *args, **kwargs):
    # messages.success(self.request, "accounts/profile.html")
    # return super(ProfileView, self).get(*args, **kwargs)


@login_required(login_url='/accounts/login/')
def welcome(request):
    from prophetcore.forms import InitIdcForm
    from django.contrib import messages
    from prophetcore.models import Idc
    idc = Idc.objects.filter(actived=True)
    index_url = reverse_lazy('prophetcore:index')
    from django.conf import settings
    if idc.exists() and not settings.DEBUG:
        messages.warning(
            request, "Initialized, locked"
        )
        return HttpResponseRedirect(index_url)
    else:
        if request.method == 'POST':
            form = InitIdcForm(request.POST)
            if form.is_valid():
                form.instance.creator = request.user
                form.save()
                request.user.onidc = form.instance
                request.user.save()
                try:
                    from django.core.management import call_command
                    call_command('loaddata', 'initial_options.json')
                except:
                    messages.error(
                        request, "loaddata initial_options.json 执行失败..."
                    )
                messages.success(
                    request, "初始化完成，请开始使用吧..."
                )
            return HttpResponseRedirect(index_url)
        else:
            form = InitIdcForm()
    return render(request, 'welcome.html', {'form': form})
