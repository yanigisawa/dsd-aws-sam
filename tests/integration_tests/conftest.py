"""Fixtures for dsd-aws-sam integration tests."""

import tomllib
from pathlib import Path
from time import sleep

import pytest

from .utils import it_helper_functions as ihf
from .utils import manage_sample_project as msp


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "skip_auto_dsd_call: skip the automatic `manage.py deploy` call for a test module",
    )


@pytest.fixture(scope="session")
def tmp_project(tmp_path_factory):
    """Copy the sample blog project into a session tmp dir, set up its venv,
    install the plugin in editable mode, and make an initial commit tagged
    INITIAL_STATE so each module can reset between runs.
    """
    sleep(0.2)
    tmp_proj_dir = tmp_path_factory.mktemp("blog_project")
    msp.setup_project(tmp_proj_dir)
    return tmp_proj_dir


# Build the parametrization list for reset_test_project: req_txt is always
# available; poetry and pipenv are only tested when installed.
_pkg_managers = ["req_txt"]
if ihf.check_package_manager_available("poetry"):
    _pkg_managers.append("poetry")
if ihf.check_package_manager_available("pipenv"):
    _pkg_managers.append("pipenv")


@pytest.fixture(scope="module", params=_pkg_managers)
def reset_test_project(request, tmp_project):
    """Reset the shared tmp project before each test module runs, once per
    package manager."""
    msp.reset_test_project(tmp_project, request.param)


@pytest.fixture(scope="module", autouse=True)
def run_dsd(reset_test_project, tmp_project, request):
    """Run `manage.py deploy` against the tmp project before each module's
    tests execute. Test modules that need to call deploy themselves (e.g. with
    custom CLI args) should set `pytestmark = pytest.mark.skip_auto_dsd_call`.
    """

    if request.node.get_closest_marker("skip_auto_dsd_call"):
        return

    msp.call_deploy(tmp_project, "python manage.py deploy")


@pytest.fixture()
def pkg_manager(request):
    """Expose the current package-manager parameter from reset_test_project."""
    return request.node.callspec.params.get("reset_test_project")


@pytest.fixture(scope="session")
def dsd_version():
    """Version of django-simple-deploy under test, used to render reference
    files that include a pinned version string.

    Reads from the adjacent django-simple-deploy source directory's
    pyproject.toml — that is the source installed into each tmp venv, so its
    version matches what `pip install -e` writes into the generated
    requirements file.
    """
    plugin_root = Path(__file__).parents[2]
    pyproject = plugin_root.parent / "django-simple-deploy" / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip(f"django-simple-deploy source not found at {pyproject}.")
    data = tomllib.loads(pyproject.read_text())

    return data["project"]["version"]
