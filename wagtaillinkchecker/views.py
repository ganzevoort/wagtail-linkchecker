from functools import lru_cache

from django.db.models import F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from wagtail.admin import messages
from wagtail.admin.panels import (
    ObjectList,
    extract_panel_definitions_from_model_class,
)
from wagtail.admin.ui.components import Component
from wagtail.models import Site

from .forms import SitePreferencesForm
from .models import SitePreferences, Scan
from .pagination import paginate
from .scanner import get_celery_worker_status


@lru_cache()
def get_edit_handler(model):
    panels = extract_panel_definitions_from_model_class(model, ['site'])

    return ObjectList(panels).bind_to_model(model)


class ScanPanel(Component):
    template_name = 'wagtaillinkchecker/scanpanel.html'


class BrokenPanel(ScanPanel):

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        context['sectionname'] = 'broken'
        context['sectiontitle'] = _('Broken Links')
        context['links'] = parent_context['links'].broken_links()
        return context


class WorkingPanel(ScanPanel):

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        context['sectionname'] = 'working'
        context['sectiontitle'] = _('Working Links')
        context['links'] = parent_context['links'].working_links()
        return context


class TodoPanel(ScanPanel):

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        context['sectionname'] = 'todo'
        context['sectiontitle'] = _('Links To Be Scanned')
        context['links'] = parent_context['links'].non_scanned_links()
        return context


def scan(request, scan_pk):
    scan = get_object_or_404(Scan, pk=scan_pk)
    panels = [
        BrokenPanel(),
        WorkingPanel(),
        TodoPanel(),
    ]
    groupby = request.GET.get('groupby')
    groupables = {
        'status_code': _('Status code'),
        'domainname': _('Domain name'),
        'page__title': _('Page'),
    }
    if groupby not in groupables:
        groupby = 'status_code'
    return render(request, 'wagtaillinkchecker/scan.html', {
        'panels': panels,
        'scan': scan,
        'groupables': groupables,
        'groupby': groupby,
        'links': (
            scan.links
            .annotate(groupby=F(groupby))
            .order_by('groupby', 'status_code', 'domainname', 'url')
        ),
    })


def index(request):
    site = Site.find_for_request(request)
    scans = Scan.objects.filter(site=site).order_by('-scan_started')

    paginator, page = paginate(request, scans)

    return render(request, 'wagtaillinkchecker/index.html', {
        'page': page,
        'paginator': paginator,
        'scans': scans
    })


def stop(request, scan_pk):
    scan = get_object_or_404(Scan, pk=scan_pk)

    if scan.scan_finished:
        return redirect('wagtaillinkchecker')

    if request.method == 'POST':
        scan.scan_finished = timezone.now()
        scan.save()
        messages.success(request, _('The scan was stopped.'))
        return redirect('wagtaillinkchecker')

    return render(request, 'wagtaillinkchecker/stop.html', {
        'scan': scan,
    })


def delete(request, scan_pk):
    scan = get_object_or_404(Scan, pk=scan_pk)

    if request.method == 'POST':
        scan.delete()
        messages.success(request, _(
            'The scan results were successfully deleted.'))
        return redirect('wagtaillinkchecker')

    return render(request, 'wagtaillinkchecker/delete.html', {
        'scan': scan,
    })


def settings(request):
    site = Site.find_for_request(request)
    instance, created = SitePreferences.objects.get_or_create(site=site)
    form = SitePreferencesForm(instance=instance)
    form.instance.site = site
    object_list = get_edit_handler(SitePreferences)

    if request.method == "POST":
        instance = SitePreferences.objects.filter(site=site).first()
        form = SitePreferencesForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _(
                'Link checker settings have been updated.'))
            return redirect('wagtaillinkchecker_settings')
        else:
            messages.error(request, _(
                'The form could not be saved due to validation errors'))
    else:
        form = SitePreferencesForm(instance=instance)
        edit_handler = object_list.get_bound_panel(
            instance=SitePreferences, form=form, request=request
        )

    return render(request, 'wagtaillinkchecker/settings.html', {
        'form': form,
        'edit_handler': edit_handler,
    })


def run_scan(request):
    site = Site.find_for_request(request)
    celery_status = get_celery_worker_status()
    if 'ERROR' not in celery_status:
        scan = Scan.objects.create(site=site)
        scan.scan_all_pages()
    else:
        messages.warning(request, _(
            'No celery workers are running, the scan was not conducted.'))

    return redirect('wagtaillinkchecker')
