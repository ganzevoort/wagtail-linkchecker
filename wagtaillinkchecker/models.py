from urllib.parse import urlparse, urljoin
from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.db.utils import DataError
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from wagtail.models import Site, Page


class SitePreferences(models.Model):
    site = models.OneToOneField(
        Site,
        unique=True, db_index=True, editable=False, on_delete=models.CASCADE,
    )
    automated_scanning = models.BooleanField(
        default=False,
        help_text=_(
            'Conduct automated sitewide scans for broken links, '
            'and send emails if a problem is found.'),
        verbose_name=_('Automated Scanning')
    )
    email_sender = models.EmailField(
        default=settings.DEFAULT_FROM_EMAIL,
        help_text=_('Sender of the problem report emails'),
    )
    email_recipient = models.EmailField(
        blank=True,
        default='',
        help_text=_(
            'Recipient of the full problem report emails '
            '(page owners get reports too)'),
    )


class Scan(models.Model):
    scan_finished = models.DateTimeField(blank=True, null=True)
    scan_started = models.DateTimeField(auto_now_add=True)
    site = models.ForeignKey(
        Site, db_index=True, editable=False, on_delete=models.CASCADE)

    @property
    def is_finished(self):
        return self.scan_finished is not None

    def add_link(self, url, page=None, follow=False):
        if not url or url.startswith('#'):
            return
        base_url = page.full_url if page else self.scan.root_url
        link_url = urljoin(base_url, url)
        parsed = urlparse(link_url)
        if parsed.scheme not in ('http', 'https'):
            return
        if self.links.filter(url=link_url).exists():
            return  # already exists, fine
        try:
            link = self.links.create(url=link_url, page=page, follow=follow)
            # add parsed.netloc so links can easily be grouped by sitename
        except DataError:
            return  # probably url too long
        return link

    def add_links(self, urls, page=None):
        new_links = []
        for url in urls:
            if newlink := self.add_link(url, page=page):
                new_links.append(newlink)
        return new_links

    def result(self):
        return _('{0} broken links found out of {1} links').format(
            self.broken_link_count(),
            self.links.count(),
        )

    def __str__(self):
        return 'Scan - {0}'.format(self.scan_started.strftime('%d/%m/%Y'))


class ScanLinkQuerySet(models.QuerySet):

    def valid(self):
        return self.filter(invalid=False)

    def non_scanned_links(self):
        return self.filter(crawled=False)

    def broken_links(self):
        return self.valid().filter(broken=True)

    def crawled_links(self):
        return self.valid().filter(crawled=True)

    def invalid_links(self):
        return self.valid().filter(invalid=True)

    def working_links(self):
        return self.valid().filter(broken=False, crawled=True)


class ScanLink(models.Model):
    scan = models.ForeignKey(Scan, related_name='links',
                             on_delete=models.CASCADE)
    url = models.URLField(max_length=500)

    # If the contents found at that url should be scanned for additional links
    follow = models.BooleanField(default=False)

    # If the link has been crawled
    crawled = models.BooleanField(default=False)

    # Link is not necessarily broken, it is invalid (eg a tel link or
    # not an actual url)
    invalid = models.BooleanField(default=False)

    # If the link is broken or not
    broken = models.BooleanField(default=False)

    # Error returned from link, if it is broken
    status_code = models.IntegerField(blank=True, null=True)
    error_text = models.TextField(blank=True, null=True)

    # Page where link was found
    page = models.ForeignKey(Page, null=True, on_delete=models.SET_NULL)

    # Page this link was on was deleted
    page_deleted = models.BooleanField(default=False)

    page_slug = models.CharField(max_length=512, null=True, blank=True)

    objects = ScanLinkQuerySet.as_manager()

    class Meta:
        unique_together = [('url', 'scan')]

    def __str__(self):
        return self.url

    @property
    def page_is_deleted(self):
        return self.page_deleted and self.page_slug

    def check_link(self, run_sync=False, verbosity=0):
        from wagtaillinkchecker.tasks import check_link

        if run_sync:
            check_link(self.pk, run_sync, verbosity)
        else:
            check_link.delay(self.pk, run_sync, verbosity)


@receiver(pre_delete, sender=Page)
def delete_tag(instance, **kwargs):
    ScanLink.objects.filter(page=instance).update(
        page_deleted=True, page_slug=instance.slug)
