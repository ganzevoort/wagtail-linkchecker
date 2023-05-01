import requests
from django.utils.translation import gettext_lazy as _

from siacms.celery import app

from http import HTTPStatus
from .models import Scan


def get_celery_worker_status():
    ERROR_KEY = "ERROR"
    try:
        from celery.app.control import Control
        insp = Control(app).inspect()
        d = insp.stats()
        if not d:
            d = {ERROR_KEY: 'No running Celery workers were found.'}
    except IOError as e:
        from errno import errorcode
        msg = "Error connecting to the backend: " + str(e)
        if len(e.args) > 0 and errorcode.get(e.args[0]) == 'ECONNREFUSED':
            msg += ' Check that the RabbitMQ server is running.'
        d = {ERROR_KEY: msg}
    except ImportError as e:
        d = {ERROR_KEY: str(e)}
    return d


def get_url(url, page, site):
    data = {
        'url': url,
        'page': page,
        'site': site,
        'error': False,
        'invalid_schema': False
    }
    response = None
    try:
        response = requests.get(url, verify=True, timeout=60)
        data['response'] = response
    except (
        requests.exceptions.InvalidSchema,
        requests.exceptions.MissingSchema,
    ):
        data['invalid_schema'] = True
        return data
    except requests.exceptions.ConnectionError:
        data['error'] = True
        data['error_message'] = _('There was an error connecting to this site')
        return data
    except requests.exceptions.RequestException as e:
        data['error'] = True
        # data['status_code'] = response.status_code
        data['error_message'] = type(e).__name__ + ': ' + str(e)
        return data

    else:
        if response.status_code not in range(100, 400):
            data['error'] = True
            data['status_code'] = response.status_code
            try:
                data['error_message'] = HTTPStatus(response.status_code).phrase
            except ValueError:
                if response.status_code in range(400, 500):
                    data['error_message'] = 'Client error'
                elif response.status_code in range(500, 600):
                    data['error_message'] = 'Server Error'
                else:
                    data['error_message'] = (
                        "Error: Unknown HTTP Status Code '{0}'".format(
                            response.status_code))
        return data


def clean_url(url, site):
    if url and url != '#':
        if url.startswith('/'):
            url = site.root_url + url
    else:
        return None
    return url


def broken_link_scan(site, run_sync=False, verbosity=0):
    pages = site.root_page.get_descendants(inclusive=True).live().public()
    scan = Scan.objects.create(site=site)

    links = []
    for page in pages:
        url = page.full_url
        if verbosity > 1:
            print(f"Checking {url}")
        link = scan.add_link(page=page, url=url)
        links.append(link)

    for link in links:
        link.check_link(run_sync, verbosity)

    return scan
