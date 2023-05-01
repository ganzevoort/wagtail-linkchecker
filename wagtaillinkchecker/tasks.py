from celery import shared_task
from bs4 import BeautifulSoup
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .scanner import get_url, clean_url
from .models import ScanLink


@shared_task
def check_link(link_pk, run_sync=False, verbosity=1):
    link = ScanLink.objects.get(pk=link_pk)
    scan = link.scan
    site = scan.site

    url = get_url(link.url, link.page, site)
    link.status_code = url.get('status_code')

    if url['error']:
        link.broken = True
        link.error_text = url['error_message']

    elif url['invalid_schema']:
        link.invalid = True
        link.error_text = _('Link was invalid')

    elif link.page.full_url == link.url:
        soup = BeautifulSoup(url['response'].content, 'html5lib')
        anchors = soup.find_all('a')
        images = soup.find_all('img')
        link_urls = []
        new_links = []

        for anchor in anchors:
            link_urls.append(anchor.get('href'))
        for image in images:
            link_urls.append(image.get('src'))

        for link_url in link_urls:
            link_url = clean_url(link_url, site)
            if verbosity > 1:
                print(f"cleaned link_url: {link_url}")
            if link_url:
                new_link = scan.add_link(page=link.page, url=link_url)
                if new_link:
                    new_links.append(new_link)
        for new_link in new_links:
            new_link.check_link(run_sync, verbosity)

    link.crawled = True
    link.save()

    if scan.links.non_scanned_links():
        pass
    else:
        scan.scan_finished = timezone.now()
        scan.save()
