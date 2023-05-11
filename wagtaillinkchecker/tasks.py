import requests
from http import HTTPStatus
from celery import shared_task
from bs4 import BeautifulSoup

from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import ScanLink


@shared_task
def check_link(link_pk):
    link = ScanLink.objects.get(pk=link_pk)
    scan = link.scan

    if scan.scan_finished:
        return

    if scan.verbosity > 1:
        print(f"Check link {link.url} for page {link.page.id}:")

    response = None
    try:
        response = requests.get(link.url, verify=True, timeout=60)
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
            if link.follow:
                soup = BeautifulSoup(response.content, 'html5lib')
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

        else:
            link.broken = True
            try:
                link.error_text = HTTPStatus(response.status_code).phrase
            except ValueError:
                if response.status_code in range(400, 500):
                    link.error_text = _('Client error')
                elif response.status_code in range(500, 600):
                    link.error_text = _('Server Error')
                else:
                    link.error_text = (
                        _("Error: Unknown HTTP Status Code '{0}'").format(
                            response.status_code))

    link.crawled = True
    link.save()

    if not scan.links.non_scanned_links():
        scan.scan_finished = timezone.now()
        scan.save()
