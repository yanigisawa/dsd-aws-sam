"""Helper functions for integration tests of dsd-aws-sam."""

import difflib
import filecmp
import shutil
from pathlib import Path
from textwrap import dedent

import pytest


PLUGIN_ROOT = Path(__file__).parents[3]
REFERENCE_FILES_DIR = PLUGIN_ROOT / "tests" / "integration_tests" / "reference_files"


def check_reference_file(
    tmp_proj_dir,
    filepath,
    plugin_name="",
    reference_filename="",
    reference_filepath=None,
    context=None,
    tmp_path=None,
):
    """Check that the generated file matches the reference file.

    - filepath: relative path from tmp_proj_dir to the generated file
    - plugin_name: kept for compatibility with upstream signature; unused here
      because reference files always live in this plugin's reference_files dir
    - reference_filename: name of the reference file when it differs from the
      generated file's basename
    - reference_filepath: absolute path to a specific reference file
    - context: mapping of placeholder -> replacement, applied to the reference
      file before comparison
    - tmp_path: pytest tmp_path, required when context is provided; used to
      write the rendered reference file
    """
    fp_generated = tmp_proj_dir / filepath
    assert fp_generated.exists(), f"Generated file does not exist: {fp_generated}"

    if reference_filename:
        filename = Path(reference_filename)
    else:
        filename = Path(filepath).name

    if reference_filepath:
        fp_reference = reference_filepath
    else:
        fp_reference = REFERENCE_FILES_DIR / filename

    assert fp_reference.exists(), f"Reference file does not exist: {fp_reference}"

    if context:
        assert tmp_path is not None, "tmp_path is required when context is provided"
        contents = fp_reference.read_text()
        for placeholder, replacement in context.items():
            contents = contents.replace(f"{{{placeholder}}}", replacement)
        fp_reference = tmp_path / filename
        fp_reference.write_text(contents)

    if not filecmp.cmp(fp_generated, fp_reference, shallow=False):
        generated_lines = fp_generated.read_text().splitlines(keepends=True)
        reference_lines = fp_reference.read_text().splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                reference_lines,
                generated_lines,
                fromfile=f"reference: {fp_reference}",
                tofile=f"generated: {fp_generated}",
                n=3,
            )
        )
        pytest.fail(
            f"Generated file does not match reference.\n"
            f"  generated: {fp_generated}\n"
            f"  reference: {fp_reference}\n"
            f"--- diff (reference → generated) ---\n{diff}"
        )


def check_package_manager_available(pkg_manager):
    """Return True if the given package manager is on PATH."""
    if shutil.which(pkg_manager):
        return True

    msg = dedent(
        f"""
        --- To run the full set of tests, {pkg_manager.title()} should be installed. ---
        """
    )
    print(msg)
    return False
