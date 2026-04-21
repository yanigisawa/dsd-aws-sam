"""Utilities for copying, resetting, and deploying the sample blog project.

These helpers mirror the integration-test flow used in django-simple-deploy,
adapted so that dsd-aws-sam can exercise its own plugin against a fresh copy
of the sample project.
"""

import os
import subprocess
import sys
from pathlib import Path
from shlex import split
from shutil import copytree

import pytest


PLUGIN_ROOT = Path(__file__).parents[3]


def _find_sample_project():
    """Locate the sample_project/blog_project from django-simple-deploy.

    We expect dsd-aws-sam to be developed alongside django-simple-deploy, as
    siblings in the same parent directory.
    """
    candidate = PLUGIN_ROOT.parent / "django-simple-deploy" / "sample_project" / "blog_project"
    if not candidate.exists():
        pytest.skip(
            f"Sample project not found at {candidate}. "
            "Clone django-simple-deploy as a sibling of dsd-aws-sam to run integration tests."
        )
    return candidate


def _uv_available():
    try:
        subprocess.run(["uv", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False
    return True


def _venv_python(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_pip(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def setup_project(tmp_proj_dir):
    """Copy the sample project into tmp_proj_dir, create a venv, install
    requirements and the local editable versions of django-simple-deploy and
    dsd-aws-sam, and make an initial git commit tagged INITIAL_STATE."""

    sample_project_dir = _find_sample_project()
    copytree(sample_project_dir, tmp_proj_dir, dirs_exist_ok=True)

    venv_dir = tmp_proj_dir / "b_env"
    uv = _uv_available()

    if uv:
        subprocess.run(["uv", "venv", str(venv_dir)], check=True)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    requirements_path = tmp_proj_dir / "requirements.txt"
    dsd_root = PLUGIN_ROOT.parent / "django-simple-deploy"
    vendor_dir = dsd_root / "vendor"

    if uv:
        py = _venv_python(venv_dir)
        install_cmd = [
            "uv", "pip", "install", "--python", str(py),
        ]
        if vendor_dir.exists():
            install_cmd += ["--no-index", "--find-links", str(vendor_dir)]
        install_cmd += ["-r", str(requirements_path)]
        subprocess.run(install_cmd, check=True)
    else:
        pip = _venv_pip(venv_dir)
        install_cmd = [str(pip), "install"]
        if vendor_dir.exists():
            install_cmd += ["--no-index", "--find-links", str(vendor_dir)]
        install_cmd += ["-r", str(requirements_path)]
        subprocess.run(install_cmd, check=True)

    # Install editable django-simple-deploy and this plugin.
    if uv:
        py = _venv_python(venv_dir)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(py), "-e", str(dsd_root)],
            check=True,
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(py), "-e", str(PLUGIN_ROOT)],
            check=True,
        )
    else:
        pip = _venv_pip(venv_dir)
        subprocess.run([str(pip), "install", "-e", str(dsd_root)], check=True)
        subprocess.run([str(pip), "install", "-e", str(PLUGIN_ROOT)], check=True)

    os.chdir(tmp_proj_dir)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "branch", "-m", "main"])
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "config", "user.name", "Test", "."], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com", "."], check=True)
    subprocess.run(["git", "commit", "-am", "Initial commit."], check=True)
    subprocess.run(["git", "tag", "-am", "", "INITIAL_STATE"], check=True)

    _add_dsd_to_installed_apps(tmp_proj_dir)


def _add_dsd_to_installed_apps(tmp_proj_dir):
    settings_path = tmp_proj_dir / "blog" / "settings.py"
    contents = settings_path.read_text()
    contents = contents.replace(
        "# Third party apps.",
        '# Third party apps.\n    "django_simple_deploy",',
    )
    settings_path.write_text(contents)


def reset_test_project(tmp_proj_dir, pkg_manager):
    """Reset the tmp project to its INITIAL_STATE, then strip files that
    don't belong to the selected package manager, and re-add dsd to
    INSTALLED_APPS."""

    os.chdir(tmp_proj_dir)
    subprocess.run(["git", "reset", "--hard", "INITIAL_STATE"], check=True)
    subprocess.run(["git", "clean", "-fd"], check=True)

    if pkg_manager == "req_txt":
        (tmp_proj_dir / "pyproject.toml").unlink(missing_ok=True)
        (tmp_proj_dir / "Pipfile").unlink(missing_ok=True)
    elif pkg_manager == "poetry":
        (tmp_proj_dir / "requirements.txt").unlink(missing_ok=True)
        (tmp_proj_dir / "Pipfile").unlink(missing_ok=True)
    elif pkg_manager == "pipenv":
        (tmp_proj_dir / "requirements.txt").unlink(missing_ok=True)
        (tmp_proj_dir / "pyproject.toml").unlink(missing_ok=True)

    subprocess.run(
        ["git", "commit", "-am", "Removed unneeded dependency management files."]
    )

    _add_dsd_to_installed_apps(tmp_proj_dir)
    subprocess.run(
        ["git", "commit", "-am", "Added django_simple_deploy to INSTALLED_APPS."]
    )


def call_deploy(tmp_proj_dir, dsd_command):
    """Run `manage.py deploy ...` inside the tmp project's venv.

    Returns (stdout, stderr) as strings.
    """
    os.chdir(tmp_proj_dir)
    dsd_command = dsd_command.replace("deploy", "deploy --unit-testing")

    venv_dir = Path(tmp_proj_dir) / "b_env"
    python_exe = _venv_python(venv_dir)
    dsd_command = dsd_command.replace("python", python_exe.as_posix())

    proc = subprocess.Popen(
        split(dsd_command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_proj_dir,
    )
    stdout, stderr = proc.communicate()
    return stdout, stderr
