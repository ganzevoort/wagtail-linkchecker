from urllib.parse import urlparse, urljoin
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.db.utils import DataError
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel
from wagtail.models import Site, Page


def get_site_preferences(site):
    try:
        return site.sitepreferences
    except ObjectDoesNotExist:
        return SitePreferences.objects.create(site=site)


class SitePreferences(models.Model):
    site = models.OneToOneField(
        Site,
        unique=True, db_index=True, editable=False, on_delete=models.CASCADE,
    )
    automated_cleanup = models.BooleanField(
        default=False,
        help_text=_('Automatically remove old scans'),
        verbose_name=_('Automated Cleanup'),
    )
    automated_cleanup_days = models.PositiveSmallIntegerField(
        default=7,
        help_text=_('Number of days to keep scans in automated cleanup'),
        verbose_name=_('Automated Cleanup Age'),
    )
    automated_scanning = models.BooleanField(
        default=False,
        help_text=_('Conduct automated sitewide scans for broken links'),
        verbose_name=_('Automated Scanning'),
    )
    email_reports = models.BooleanField(
        default=False,
        help_text=_('Send report emails after automated scans'),
        verbose_name=_('Email Reports'),
    )
    email_sender = models.EmailField(
        default=settings.DEFAULT_FROM_EMAIL,
        help_text=_('Sender of the problem report emails'),
        verbose_name=_('Email Sender')
    )
    email_recipient = models.EmailField(
        blank=True,
        default='',
        help_text=_(
            'Recipient of the full problem report emails '
            '(page owners get reports too)'),
        verbose_name=_('Email Recipient')
    )
    user_agent = models.CharField(
        blank=True,
        default='',
        max_length=500,
        help_text=_(
            'User-Agent header to use in scans'),
        verbose_name=_('User-Agent Header')
    )

    panels = [
        MultiFieldPanel([
            FieldRowPanel([
                FieldPanel('automated_scanning'),
                FieldPanel('automated_cleanup'),
                FieldPanel('automated_cleanup_days'),
            ]),
            MultiFieldPanel([
                FieldPanel('email_reports'),
                FieldPanel('email_sender'),
                FieldPanel('email_recipient'),
            ], heading=_('Email')),
        ], heading=_('Automated Scanning')),
        FieldPanel('user_agent'),
    ]


class Scan(models.Model):
    scan_finished = models.DateTimeField(blank=True, null=True)
    scan_started = models.DateTimeField(auto_now_add=True)
    site = models.ForeignKey(
        Site, db_index=True, editable=False, on_delete=models.CASCADE)
    run_sync = models.BooleanField(default=False)
    verbosity = models.PositiveSmallIntegerField(default=0)

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
        except DataError:
            return  # probably url too long
        return link

    def add_links(self, urls, page=None):
        new_links = []
        for url in urls:
            if newlink := self.add_link(url, page=page):
                new_links.append(newlink)
        return new_links

    def scan_pages(self, pages):
        if self.verbosity:
            print(f'Scanning {len(pages)} pages...')
        links = []
        for page in pages:
            url = page.full_url
            if self.verbosity > 1:
                print(f"Page {url}, {page.id}: {page.title}")
            link = self.add_link(url, page=page, follow=True)
            if link:
                links.append(link)
        for link in links:
            link.check_link()

    def scan_all_pages(self):
        self.scan_pages(
            self.site.root_page.get_descendants(inclusive=True)
            .live().public()
            .order_by('-latest_revision_created_at')
        )

    def __str__(self):
        return 'Scan - {0}'.format(self.scan_started.strftime('%d/%m/%Y'))


class ScanLinkQuerySet(models.QuerySet):

    def valid(self):
        return self.filter(invalid=False)

    def invalid_links(self):
        return self.filter(invalid=True)

    def non_scanned_links(self):
        return self.filter(crawled=False)

    def broken_links(self):
        return self.filter(broken=True)

    def crawled_links(self):
        return self.valid().filter(crawled=True)

    def working_links(self):
        return self.valid().filter(broken=False, crawled=True)


class ScanLink(models.Model):
    scan = models.ForeignKey(Scan, related_name='links',
                             on_delete=models.CASCADE)
    url = models.URLField(max_length=500)

    # Domain name part (netloc) of the url, for easy grouping
    domainname = models.CharField(default='', blank=True, max_length=500)

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

    def save(self, *args, **kwargs):
        parsed = urlparse(self.url)
        # add parsed.netloc so links can easily be grouped by domainname
        self.domainname = parsed.netloc
        super().save(*args, **kwargs)

    def check_link(self):
        from wagtaillinkchecker.tasks import check_link

        if self.scan.run_sync:
            check_link(self.pk)
        else:
            check_link.delay(self.pk)


@receiver(pre_delete, sender=Page)
def delete_tag(instance, **kwargs):
    ScanLink.objects.filter(page=instance).update(
        page_deleted=True, page_slug=instance.slug)
