"""Offline tests for run_ref_downloader.py — DOI detection + path sanitization."""

from run_ref_downloader import doi_to_project_name, looks_like_doi


def test_looks_like_doi():
    assert looks_like_doi("10.1021/jacs.5c05017")
    assert looks_like_doi("  10.99/foo  ")  # whitespace tolerated
    assert not looks_like_doi("/path/to/file.pdf")
    assert not looks_like_doi("not a doi")
    assert not looks_like_doi("")
    assert not looks_like_doi("11.99/notreallydoi")  # only 10. prefix counts


def test_doi_to_project_name_filters_windows_illegal_chars():
    """Project-name sanitizer strips characters that are invalid in Windows paths."""
    # Forward slashes inside the path: takes only the suffix after the last /
    assert doi_to_project_name("10.99/path/with/slashes") == "slashes"
    # < > : " | ? * are all replaced with _
    assert doi_to_project_name("10.99/foo<bar>baz") == "foo_bar_baz"
    assert doi_to_project_name('10.99/quoted"name') == "quoted_name"
    assert doi_to_project_name("10.99/with*star?and|pipe") == "with_star_and_pipe"
    # Pure dots / spaces are stripped; resulting empty name falls back to placeholder
    assert doi_to_project_name("10.99/.") == "unnamed_project"
