from collections import namedtuple

import arrow
import structlog
from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
from raven.contrib.django.raven_compat.models import client
from slacker import Error as SlackError
from slacker import Slacker

from .check_discovery import CHECKS
from .models import Issue

log = structlog.get_logger()
slack = Slacker(settings.SLACK_TOKEN)

Result = namedtuple("Result", ["issue_key", "is_found", "details"], defaults=(None,))
CodePatch = namedtuple(
    "CodePatch",
    ["action", "file_path", "content", "previous_path"],
    defaults=(None, None),
)
RequestPatch = namedtuple(
    "RequestPatch", ["url", "method", "headers", "body"], defaults=(None, None)
)


class CheckContext:  # pylint: disable=too-many-instance-attributes
    Result = Result
    CodePatch = CodePatch
    RequestPatch = RequestPatch

    def __init__(self, repository, fake_path):
        self.owner = repository.owner
        self.name = repository.name
        self.repo_url = repository.url
        self.remote_id = repository.remote_id
        self.provider = repository.provider
        self.path = fake_path
        self.languages = repository.languages_from_analytics
        self.project_type = repository.project_type


def determine_issue_status(is_found, old_status):
    if is_found:
        if old_status == Issue.Status.NOT_FOUND.value:
            return Issue.Status.NEW.value

        if old_status == Issue.Status.FIXED.value:
            return Issue.Status.REOPENED.value

    else:
        if old_status != Issue.Status.NOT_FOUND.value:
            return Issue.Status.FIXED.value

    return old_status


def create_issue(issue_repo, issue_key, is_found, details=None):
    status = Issue.Status.NEW.value if is_found else Issue.Status.NOT_FOUND.value
    Issue.objects.create(
        repository=issue_repo, kind_key=issue_key, status=status, details=details
    )


def update_issue(issue: Issue, is_found, details=None):
    if issue.details != details:
        issue.details = details
    issue.status = determine_issue_status(is_found, issue.status)
    issue.last_check = arrow.utcnow().datetime
    issue.deleted = False
    issue.save()

    notify_status_change(issue)


def notify_status_change(issue: Issue):
    if Issue.Status(issue.status) in [Issue.Status.NEW, Issue.Status.REOPENED]:
        site = Site.objects.get_current()
        audit_url = reverse(
            "audit_report",
            args=("services", issue.repository.owner, issue.repository.name),
        )
        text = "{status} issue {issue} on <{repo.url}|{repo.name}>.".format(
            status=issue.status.title(),
            issue=f"<http://{site.domain}{audit_url}|{issue.kind.title}>",
            repo=issue.repository,
        )
        for channel in issue.repository.services.values_list(
            "slack_channel", flat=True
        ):
            try:
                slack.chat.post_message(channel, text)
            except SlackError as error:
                log.exception("auditing.update_issue.slack_error", error=repr(error))


def save_check_result(issue_repo, issue_key, is_found, details=None):
    if details is None:
        details = {}

    # we ignore/clear details for not found (or fixed) issues
    if not is_found:
        details = {}

    try:
        issue = issue_repo.issues.get(kind_key=issue_key)
    except Issue.DoesNotExist:
        create_issue(issue_repo, issue_key, is_found, details=details)
    else:
        update_issue(issue, is_found, details=details)


def check_repository(checks, repository, fake_path):
    context = CheckContext(repository, fake_path)
    for check in checks:
        try:
            for result in check(context):
                # skip unknown results
                if result.is_found is None:
                    continue

                if result.is_found:
                    log.info(
                        "auditing.check.result_found",
                        repo_id=repository.id,
                        check=check.__name__,
                        check_module=check.__module__,
                        issue=result.issue_key,
                    )

                yield result
        except:
            log.exception(
                "auditing.check.error",
                repo_id=repository.id,
                check=check.__name__,
                check_module=check.__module__,
            )
            client.captureException(fingerprint=[check.__module__, check.__name__])


def run_checks_and_save_results(checks, repository, fake_path):
    found_issues = set()

    for result in check_repository(checks, repository, fake_path):
        found_issues.add(result.issue_key)
        save_check_result(repository, result.issue_key, result.is_found, result.details)

    if checks == CHECKS:
        repository.issues.exclude(kind_key__in=found_issues).update(deleted=True)
