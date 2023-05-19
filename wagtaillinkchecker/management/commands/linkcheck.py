from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand

from wagtail.models import Site

from wagtaillinkchecker.models import Scan, get_site_preferences
from wagtaillinkchecker.report import email_report


def cleanup(site, preferences, verbosity):
    cutoff_age = timedelta(days=preferences.automated_cleanup_days)
    cutoff = timezone.now() - cutoff_age
    for scan in Scan.objects.filter(site=site, scan_started__lt=cutoff):
        if verbosity:
            print(f"Automated cleanup: remove {scan}")
        scan.delete()


def runscan(site, preferences, verbosity):
    scan = Scan.objects.create(site=site, run_sync=True, verbosity=verbosity)
    scan.scan_all_pages()

    if verbosity:
        total_links = scan.links.crawled_links()
        broken_links = scan.links.broken_links()
        print(
            f'Found {len(total_links)} total links, '
            f'with {len(broken_links)} broken links.')

    if preferences.email_reports:
        messages = email_report(scan)
        if verbosity:
            print(f'Sent {len(messages)} messages')
    else:
        if verbosity:
            print('Will not send any emails')


class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        site = Site.objects.filter(is_default_site=True).first()
        preferences = get_site_preferences(site)
        verbosity = kwargs.get('verbosity', 1)

        if preferences.automated_cleanup:
            cleanup(site, preferences, verbosity)
        elif verbosity:
            print('Automated cleanup not enabled')

        if preferences.automated_scanning:
            runscan(site, preferences, verbosity)
        elif verbosity:
            print('Automated scanning not enabled')
