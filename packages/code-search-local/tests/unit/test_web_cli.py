"""The ``web`` command hands the service token to the dashboard through the URL fragment."""

import json
import os
import stat
import time
import webbrowser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from click.testing import CliRunner

from code_search_local import cli, constants
from code_search_local.cli import main
from code_search_local.config import Settings
from code_search_local.events import runtime_directory
from code_search_local.service import token_for
from tests import constants as test_constants


class LaunchPage(HTMLParser):
    """The redirect targets of a launch page, as a browser would decode them."""

    def __init__(self, source):
        super().__init__()
        self.tags, self.scripts, self.in_script = [], [], False
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self.in_script = tag == test_constants.HTML_TAG_SCRIPT
        if self.in_script:
            self.scripts.append("")

    def handle_endtag(self, tag):
        self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1] += data

    def targets(self):
        """Return the meta refresh content, the script's target and the link target."""
        (script,) = self.scripts
        assert script.startswith(test_constants.LAUNCH_SCRIPT_PREFIX)
        assert script.endswith(test_constants.LAUNCH_SCRIPT_SUFFIX)
        (refresh,) = (
            attributes[test_constants.HTML_ATTRIBUTE_CONTENT]
            for tag, attributes in self.tags
            if tag == test_constants.HTML_TAG_META
            and attributes.get(test_constants.HTML_ATTRIBUTE_HTTP_EQUIV)
            == test_constants.HTML_HTTP_EQUIV_REFRESH
        )
        (link,) = (
            attributes[test_constants.HTML_ATTRIBUTE_HREF]
            for tag, attributes in self.tags
            if tag == test_constants.HTML_TAG_LINK
        )
        target = script.removeprefix(test_constants.LAUNCH_SCRIPT_PREFIX).removesuffix(
            test_constants.LAUNCH_SCRIPT_SUFFIX
        )
        return refresh, json.loads(target), link


def run_web(monkeypatch, *arguments):
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    result = CliRunner().invoke(main, [constants.COMMAND_WEB, *arguments])
    return result, opened


def token_url():
    settings = Settings.load()
    token = token_for(settings.root, create=True)
    return token, constants.WEBAPP_TOKEN_URL_TEMPLATE.format(url=settings.url, token=token)


def launch_directory():
    return runtime_directory() / constants.APPLICATION_NAME / constants.PATH_WEBAPP_LAUNCH_DIRECTORY


def launch_pages():
    return set(launch_directory().glob(constants.WEBAPP_LAUNCH_PAGE_GLOB))


def assert_redirects_to(page, url):
    assert LaunchPage(page.read_text()).targets() == (
        test_constants.LAUNCH_REFRESH_TEMPLATE.format(url=url),
        url,
        url,
    )


def test_web_prints_the_token_url_and_opens_a_private_launch_page(monkeypatch):
    token, url = token_url()
    assert url == f"{Settings.load().url}{constants.WEBAPP_INDEX_ENDPOINT}#token={token}"
    result, opened = run_web(monkeypatch)
    assert result.exit_code == 0, result.output
    assert result.output.strip() == url
    (page,) = launch_pages()
    assert opened == [page.as_uri()]
    assert urlparse(opened[0]).scheme == test_constants.URL_SCHEME_FILE
    assert token not in opened[0]
    assert stat.S_IMODE(page.stat().st_mode) == constants.PRIVATE_FILE_MODE
    assert stat.S_IMODE(launch_directory().stat().st_mode) == constants.PRIVATE_DIRECTORY_MODE
    assert_redirects_to(page, url)


def test_web_without_opening_writes_no_launch_page(monkeypatch):
    _, url = token_url()
    result, opened = run_web(monkeypatch, constants.OPTION_NO_OPEN)
    assert result.exit_code == 0, result.output
    assert result.output.strip() == url
    assert opened == []
    assert not launch_directory().exists()


def test_launch_page_escapes_the_url_for_html_and_script():
    page = cli.launch_page(test_constants.URL_WITH_MARKUP)
    assert test_constants.URL_WITH_MARKUP not in page.read_text()
    # One script element whose string, like every attribute, decodes to the exact URL.
    assert_redirects_to(page, test_constants.URL_WITH_MARKUP)


def test_web_removes_only_stale_launch_pages(monkeypatch):
    token_url()
    directory = cli.launch_page(test_constants.URL_LAUNCH_TARGET).parent
    stale, fresh, unremovable = (
        directory
        / (constants.WEBAPP_LAUNCH_PAGE_PREFIX + name + constants.WEBAPP_LAUNCH_PAGE_SUFFIX)
        for name in (
            test_constants.PATH_STALE,
            test_constants.PATH_FRESH,
            test_constants.PATH_DIRECTORY,
        )
    )
    stale.write_text("")
    fresh.write_text("")
    # A stale entry that cannot be unlinked is skipped.
    unremovable.mkdir()
    past = time.time() - 2 * constants.WEBAPP_LAUNCH_PAGE_MAX_AGE_SECONDS
    for path in (stale, unremovable):
        os.utime(path, (past, past))
    result, opened = run_web(monkeypatch)
    assert result.exit_code == 0, result.output
    pages = launch_pages()
    assert stale not in pages
    assert {fresh, unremovable, Path(urlparse(opened[0]).path)} <= pages


def test_web_reports_an_unwritable_launch_directory(monkeypatch):
    _, url = token_url()
    runtime = runtime_directory()
    runtime.mkdir(parents=True)
    (runtime / constants.APPLICATION_NAME).write_text("")
    result, opened = run_web(monkeypatch)
    assert result.exit_code == 1
    assert url in result.output
    assert "open the URL above instead" in result.output
    assert opened == []


def test_web_requires_a_configured_service(monkeypatch):
    result, opened = run_web(monkeypatch)
    assert result.exit_code == 1
    assert "not configured" in result.output
    assert opened == []
