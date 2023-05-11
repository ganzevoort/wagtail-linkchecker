from siacms.celery import app

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


def broken_link_scan(site, run_sync=False, verbosity=0):
    pages = (
        site.root_page.get_descendants(inclusive=True)
        .live().public()
        .order_by('-latest_revision_created_at')
    )
    scan = Scan.objects.create(site=site)

    links = []
    for page in pages:
        url = page.full_url
        if verbosity > 1:
            print(f"Page {url}, {page.id}: {page.title}")
        link = scan.add_link(url, page=page, follow=True)
        if link:
            links.append(link)

    for link in links:
        link.check_link(run_sync, verbosity)

    return scan
