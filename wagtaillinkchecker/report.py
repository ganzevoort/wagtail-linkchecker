from collections import defaultdict
from wagtail.models import Page
from django.conf import settings
from django.core import mail
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist


def email_report(scan):
    try:
        sender = scan.site.sitepreferences.email_sender
        default_recipient = scan.site.sitepreferences.email_recipient
    except ObjectDoesNotExist:
        sender = settings.DEFAULT_FROM_EMAIL
        default_recipient = None

    outbox = defaultdict(list)
    name = defaultdict(str)
    broken = scan.links.broken_links()

    page_ids = broken.values_list('page_id', flat=True).distinct()
    for page in Page.objects.filter(pk__in=page_ids):
        if default_recipient:
            outbox[default_recipient].append(page)
        revisions = page.revisions.all()
        if revisions:
            revision = revisions.latest('created_at')
            if revision.user:
                recipient = revision.user.email
                if recipient and recipient != default_recipient:
                    name[recipient] = revision.user.get_full_name()
                    outbox[recipient].append(page)

    messages = []

    for recipient, pages in outbox.items():
        for page in pages:
            page.broken_links = broken.filter(page=page)

        email_message = render_to_string(
            'wagtaillinkchecker/emails/broken_links.html', {
                'user': name[recipient],
                'pages': pages,
                'base_url': scan.site.root_url,
                'site_name': settings.WAGTAIL_SITE_NAME,
                })
        email = mail.EmailMessage(
            'Broken links on page "%s"' % (pages[0].title),
            email_message,
            sender,
            [recipient])
        email.content_subtype = 'html'
        messages.append(email)

    if messages:
        connection = mail.get_connection()
        connection.open()
        connection.send_messages(messages)
        connection.close()

    return messages
