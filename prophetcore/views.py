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
    Option, Rack, Device, Online, Syslog, ContentType, Zonemap, Client
)
from prophetcore.forms import ZonemapNewForm


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

    def make_device_dynamic_change(self):
        content_type = ContentType.objects.get_for_model(Device)
        logs = Syslog.objects.filter(
            onidc_id=self.onidc_id, content_type=content_type)
        data = {}
        data['categories'] = [m.strftime("%Y-%m")
                              for m in self.make_years(logs)]
        data['moveup'] = []
        data['moving'] = []
        data['movedown'] = []
        for y in self.make_years(logs):
            nlogs = logs.filter(created__year=y.year, created__month=y.month)
            moving = nlogs.filter(
                message__contains='"units"', action_flag="修改").exclude(
                content__contains='"units": [[]').count()
            data['moving'].append(moving)
            moveup = nlogs.filter(action_flag="新增").count()
            data['moveup'].append(moveup)
            cancel_movedown = nlogs.filter(action_flag="取消下架").count()
            movedown = nlogs.filter(action_flag="下架").count()
            data['movedown'].append(movedown-cancel_movedown)
        return data

    def make_rack_dynamic_change(self):
        content_type = ContentType.objects.get_for_model(Rack)
        logs = Syslog.objects.filter(
            onidc_id=self.onidc_id, content_type=content_type)
        data = {}
        data['categories'] = [m.strftime("%Y-%m")
                              for m in self.make_years(logs)]
        data['renew'] = []
        data['release'] = []
        for y in self.make_years(logs):
            nlogs = logs.filter(created__year=y.year, created__month=y.month)
            data['renew'].append(nlogs.filter(action_flag="分配机柜").count())
            data['release'].append(nlogs.filter(action_flag="释放机柜").count())
        return data

    def make_rack_statistics(self):
        data = []
        robjects = Rack.objects.filter(onidc_id=self.onidc_id, actived=True)
        keys = Option.objects.filter(
            flag__in=['Rack-Style', 'Rack-Status'],
            actived=True)
        keys = shared_queryset(keys, self.onidc_id)
        for k in keys:
            d = []
            query = {
                k.flag.split('-')[1].lower(): k
            }
            c = robjects.filter(**query).count()
            if c > 0:
                d.append(force_text(k))
                d.append(c)
            if d:
                data.append(d)
        return data

    def make_online_statistics(self):
        data = []
        dobjects = Online.objects.filter(onidc_id=self.onidc_id)
        keys = Option.objects.filter(flag__in=['Device-Style', 'Device-Tags'])
        keys = shared_queryset(keys, self.onidc_id)
        for k in keys:
            d = []
            if k.flag == 'Device-Style':
                c = dobjects.filter(style=k).count()
            else:
                c = dobjects.filter(tags__in=[k]).count()
            if c > 0:
                d.append(force_text(k))
                d.append(c)
            if d:
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
        context['online_statistics'] = self.make_online_statistics()
        context['device_dynamic_change'] = self.make_device_dynamic_change()
        context['rack_statistics'] = self.make_rack_statistics()
        context['rack_dynamic_change'] = self.make_rack_dynamic_change()
        return context


class ProfileView(BaseRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'

    # def get(self, *args, **kwargs):
    # messages.success(self.request, "accounts/profile.html")
    # return super(ProfileView, self).get(*args, **kwargs)


class ZonemapView(BaseRequiredMixin, TemplateView):

    template_name = 'zonemap/detail.html'

    @cached_property
    def get_options(self):
        options = Option.objects.filter(actived=True)
        return shared_queryset(options, self.onidc_id)

    @cached_property
    def get_zones(self):
        return self.get_options.filter(flag='Rack-Zone')

    @cached_property
    def get_zone(self):
        ''' get current zone return zone instance'''
        zone_id = self.request.GET.get('zone_id', None)
        try:
            zone = self.get_zones.get(pk=int(zone_id))
        except BaseException:
            if self.get_zones.filter(master=True).exists():
                zone = self.get_zones.filter(master=True).first()
            else:
                zone = None
        return zone

    def get_mode(self):
        action = self.request.GET.get('action', 'show')
        return action

    def get_racks(self):
        if self.get_zone:
            return Rack.objects.filter(zone_id=self.get_zone)
        return None

    def get_rack_statistics(self):
        data = []
        keys = self.get_options.filter(flag__in=['Rack-Style', 'Rack-Status'])
        ''' id, color, text, flag, description, count '''
        for k in keys:
            query = {
                k.flag.split('-')[1].lower(): k
            }
            if self.get_racks():
                c = self.get_racks().filter(**query).count()
                item = dict(
                    id=k.id,
                    color=k.color,
                    count=c,
                    flag=k.flag,
                    text=k.text,
                    description=k.description,
                )
                data.append(item)
        return data

    def get_cells(self):
        filters = {'onidc_id': self.onidc_id, 'zone': self.get_zone}
        cells = Zonemap.objects.filter(**filters).order_by("row", "col")
        return cells

    def get_clients(self):
        if self.get_racks() is not None:
            exc = list(self.get_racks().values_list(
                'client_id', flat=True).exclude(client=None))
            clients = Client.objects.filter(pk__in=exc)
            return clients
        return None

    @cached_property
    def max_col(self):
        from django.db.models import Max
        return self.get_cells().aggregate(Max('col'))['col__max']

    def post(self, request, *args, **kwargs):
        if self.get_zone and self.get_mode() == 'layout':
            form = ZonemapNewForm(request.POST)
            if form.is_valid():
                zone_id = form.cleaned_data.get('zone_id')
                rows = form.cleaned_data.get('rows')
                cols = form.cleaned_data.get('cols')
                onidc_id = request.user.onidc.id
                zone_id = self.get_zone.id
                creator_id = request.user.id
                cells = []
                for row in range(rows):
                    for col in range(cols):
                        point = Zonemap.objects.filter(
                            zone_id=zone_id, row=row, col=col)
                        if not point.exists():
                            cells.append(Zonemap(
                                onidc_id=onidc_id,
                                zone_id=zone_id,
                                creator_id=creator_id,
                                row=row,
                                col=col,
                            ))
                Zonemap.objects.bulk_create(cells)
            redirect_to = reverse_lazy('prophetcore:zonemap')
            return HttpResponseRedirect('{}?zone_id={}'.format(
                redirect_to, self.get_zone.id))
        if self.get_zone and self.get_mode() == 'config':
            if request.is_ajax():
                cell_id = request.POST.get('cell_id', None)
                rack_id = request.POST.get('rack_id', None)
                cell_desc = request.POST.get('cell_desc', None)
                try:
                    cell = Zonemap.objects.get(pk=cell_id)
                except:
                    cell = None
                if cell is not None:
                    cell.rack_id = rack_id
                    cell.desc = cell_desc
                    cell.save()
                    data = {
                        'cell_id': cell.pk,
                        'rack_id': cell.rack_id,
                        'cell_desc': cell.desc,
                        'messages': "更新成功",
                    }
                    return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super(ZonemapView, self).get_context_data(**kwargs)
        from prophetcore.actions import construct_model_meta
        from django.apps import apps
        model = apps.get_model('prophetcore', 'zonemap')
        title = self.get_zone
        meta, _ = construct_model_meta(self.request, model, title)
        if self.get_mode() == 'layout':
            form = ZonemapNewForm(zone_id=self.get_zone.id)
        else:
            form = None
        if self.get_mode() == 'config':
            incells = list(Zonemap.objects.filter(
                zone_id=self.get_zone.id).values_list(
                    'rack_id', flat=True).exclude(rack=None))
            rackswap = Rack.objects.filter(zone_id=self.get_zone.id).exclude(
                pk__in=incells).order_by('-name')
        else:
            incells = rackswap = None
        _extra_cxt = {
            'zones': self.get_zones,
            'current_zone': self.get_zone,
            'meta': meta,
            'form': form,
            'incells': incells,
            'clients': self.get_clients(),
            'rackswap': rackswap,
            'config': self.get_mode() == 'config',
            'racks': self.get_racks(),
            'cells': self.get_cells(),
            'statistics': self.get_rack_statistics(),
            'max_col': self.max_col,
        }
        context.update(_extra_cxt)
        return context


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
