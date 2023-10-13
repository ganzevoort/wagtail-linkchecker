import requests
from http import HTTPStatus
from celery import shared_task
from bs4 import BeautifulSoup

from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import ScanLink, get_site_preferences


def link_is_ok(link, content):
    scan = link.scan
    preferences = get_site_preferences(scan.site)
    if link.follow:
        soup = BeautifulSoup(content, 'html5lib')
        new_links = scan.add_links(
            [anchor.get('href') for anchor in soup.find_all('a')] +
            [image.get('src') for image in soup.find_all('img')],
            page=link.page,
        )
        if new_links and scan.verbosity > 1:
            print("New links:")
            for new_link in new_links:
                print(f"\t{new_link.url}")
        for new_link in new_links:
            new_link.check_link()


def link_is_broken(link):
    link.broken = True
    try:
        link.error_text = HTTPStatus(link.status_code).phrase
    except ValueError:
        if link.status_code in range(400, 500):
            link.error_text = _('Client error')
        elif link.status_code in range(500, 600):
            link.error_text = _('Server Error')
        else:
            link.error_text = (
                _("Error: Unknown HTTP Status Code '{0}'").format(
                    link.status_code))


@shared_task
def check_link(link_pk):
    link = ScanLink.objects.get(pk=link_pk)
    scan = link.scan
    preferences = get_site_preferences(scan.site)

    if scan.scan_finished:
        return
    if scan.verbosity > 1:
        print(f"Check link {link.url} for page {link.page.id}:")

    try:
        response = requests.get(
            link.url,
            verify=True,
            timeout=60,
            headers={
                'Content-Type': 'text/html; charset=utf-8',
                'User-Agent': preferences.user_agent,
            },
        )
    except (
        requests.exceptions.InvalidSchema,
        requests.exceptions.MissingSchema,
    ):
        link.invalid = True
        link.error_text = _('Link was invalid')
    except requests.exceptions.ConnectionError:
        link.broken = True
        link.error_text = _('There was an error connecting to this site')
    except requests.exceptions.RequestException as e:
        link.broken = True
        link.error_text = type(e).__name__ + ': ' + str(e)

    else:
        link.status_code = response.status_code
        if response.status_code in range(100, 400):
            link_is_ok(link, response.content)
        else:
            link_is_broken(link)

    link.crawled = True
    link.save()

    if not scan.links.non_scanned_links():
        scan.scan_finished = timezone.now()
        scan.save()
