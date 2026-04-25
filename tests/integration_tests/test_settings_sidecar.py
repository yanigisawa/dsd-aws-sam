"""Tests for the sidecar strategy used on non-stock settings layouts.

These tests convert the shared sample project into a split-settings layout
(cookiecutter-style `blog/settings/{base,production}.py`) and then run the
deploy. The plugin should detect that the target file is not stock and
generate a sidecar `aws_sam_settings.py` instead of editing assignments in
place.
"""

import subprocess
from textwrap import dedent

import pytest

from tests.integration_tests.utils import it_helper_functions as hf
from tests.integration_tests.utils import manage_sample_project as msp


pytestmark = pytest.mark.skip_auto_dsd_call


@pytest.fixture
def split_settings_project(tmp_project):
    """Rewrite the tmp project into a `blog/settings/` split-settings layout
    and update manage.py's DJANGO_SETTINGS_MODULE accordingly, then run
    deploy against it. The session-scoped tmp_project is reset between
    modules via reset_test_project, so no explicit teardown is needed.
    """
    msp.reset_test_project(tmp_project, "req_txt")
    _mutate_to_split_layout(tmp_project)
    msp.call_deploy(tmp_project, "python manage.py deploy")
    return tmp_project


def _mutate_to_split_layout(tmp_project):
    """Move blog/settings.py -> blog/settings/{base,production}.py.

    Leaves the original INSTALLED_APPS (and the dsd entry) intact in base.py;
    production.py imports from base and overrides DEBUG so the stock-layout
    markers will not match.
    """
    project_dir = tmp_project / "blog"
    old_settings = project_dir / "settings.py"
    assert old_settings.exists(), "stock settings.py should exist before mutation"

    original = old_settings.read_text()
    old_settings.unlink()

    # base.py lives one directory deeper than the old settings.py, so BASE_DIR
    # needs an extra `.parent` to keep pointing at the repo root.
    original = original.replace(
        "BASE_DIR = Path(__file__).resolve().parent.parent",
        "BASE_DIR = Path(__file__).resolve().parent.parent.parent",
    )

    settings_pkg = project_dir / "settings"
    try:
        settings_pkg.mkdir()
    except FileExistsError:
        pass
        # pytest.skip(f"settings/ directory already exists at {settings_pkg}; cannot mutate to split-settings layout.")
    (settings_pkg / "__init__.py").write_text("")
    (settings_pkg / "base.py").write_text(original)
    (settings_pkg / "production.py").write_text(
        dedent(
            """\
            from .base import *  # noqa: F401,F403

            DEBUG = False
            """
        )
    )

    manage_py = tmp_project / "manage.py"
    manage_py.write_text(
        manage_py.read_text().replace("blog.settings", "blog.settings.production")
    )

    # dsd core refuses to run with a dirty tree; commit the mutations.
    subprocess.run(["git", "add", "-A"], cwd=tmp_project, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Convert to split-settings layout."],
        cwd=tmp_project,
        check=True,
    )


def test_sidecar_file_created(split_settings_project):
    """Sidecar module is written next to the active settings file."""
    sidecar = split_settings_project / "blog" / "settings" / "aws_sam_settings.py"
    assert sidecar.exists(), f"sidecar should exist at {sidecar}"

    contents = sidecar.read_text()
    # Spot-check the env-var reads we expect.
    assert "DJANGO_SECRET_KEY" in contents
    assert "STATIC_FILES_BUCKET" in contents
    assert "storages.backends.s3boto3.S3StaticStorage" in contents


def test_sidecar_matches_reference(split_settings_project):
    """Full content of sidecar matches reference_files/aws_sam_settings.py."""
    hf.check_reference_file(
        split_settings_project,
        "blog/settings/aws_sam_settings.py",
        "dsd-aws-sam",
    )


def test_production_imports_sidecar(split_settings_project):
    """production.py ends with the sidecar import line."""
    production = split_settings_project / "blog" / "settings" / "production.py"
    lines = production.read_text().splitlines()
    assert "from .aws_sam_settings import *" in lines[-2:], (
        f"production.py should end with the sidecar import; tail was: {lines[-5:]}"
    )


def test_base_settings_untouched(split_settings_project):
    """base.py keeps its original stock contents -- no regex rewrites."""
    base = split_settings_project / "blog" / "settings" / "base.py"
    contents = base.read_text()
    # Each of these appears in the stock django-admin output; if the plugin
    # had fallen through to the stock-strategy rewrites, they would be gone.
    assert 'SECRET_KEY = "django-insecure-' in contents
    assert "DEBUG = True" in contents
    assert "ALLOWED_HOSTS = []" in contents
    assert "os.environ.get" not in contents
