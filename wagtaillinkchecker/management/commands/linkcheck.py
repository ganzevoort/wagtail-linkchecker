from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist

from wagtail.models import Site

from wagtaillinkchecker.scanner import broken_link_scan
from wagtaillinkchecker.report import email_report


def automated_scanning_enabled(site):
    try:
        return site.sitepreferences.automated_scanning
    except ObjectDoesNotExist:
        return False


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--do-not-send-mail',
            action='store_true',
            help='Do not send mails when finding broken links',
        )
        parser.add_argument(
            '--run-synchronously',
            action='store_true',
            help='Run checks synchronously (avoid the need for Celery)',
        )
        parser.add_argument(
            '--automated',
            action='store_true',
            help='Run checks and send emails if automated scanning is enabled',
        )

    def handle(self, *args, **kwargs):
        site = Site.objects.filter(is_default_site=True).first()
        pages = site.root_page.get_descendants(inclusive=True).live().public()
        verbosity = kwargs.get('verbosity') or 1
        automated = kwargs.get('automated')
        run_sync = automated or kwargs.get('run_synchronously')
        send_emails = automated and not kwargs.get('do_not_send_mail')

        if automated and not automated_scanning_enabled(site):
            if verbosity:
                print('Automated scanning not enabled')
            return

        if verbosity:
            print(f'Scanning {len(pages)} pages...')
        scan = broken_link_scan(site, run_sync, verbosity)
        total_links = scan.links.crawled_links()
        broken_links = scan.links.broken_links()
        if verbosity:
            print(
                f'Found {len(total_links)} total links, '
                f'with {len(broken_links)} broken links.')

        if send_emails:
            messages = email_report(scan)
            if verbosity:
                print(f'Sent {len(messages)} messages')
        else:
            if verbosity:
                print('Will not send any emails')
