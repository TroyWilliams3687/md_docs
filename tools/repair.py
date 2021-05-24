#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""
-----------
SPDX-License-Identifier: MIT
Copyright (c) 2021 Troy Williams

uuid       = 633f2088-bbe3-11eb-b9c2-33be0bb8451e
author     = Troy Williams
email      = troy.williams@bluebill.net
date       = 2021-05-23
-----------

This module will hold code to repair various problems that could occur.

- bad-links
    - relative links that don't point to the correct file

- section attributes
    - ATX headers that are missing links

--dry-run

"""

# ------------
# System Modules - Included with Python

import logging

from pathlib import Path
from datetime import datetime
from multiprocessing import Pool
from functools import partial

from difflib import get_close_matches

# ------------
# 3rd Party - From pip

import click

# ------------
# Custom Modules

from md_docs.common import relative_path

from md_docs.document import (
    MarkdownDocument,
    search,
    document_lookup,
)

from md_docs.document_validation import (
    validate_urls,
    validate_images,
)

# -------------
# Logging

log = logging.getLogger(__name__)

# -------------

# $ docs repair --dry-run links <- relative markdown links - runs the validate mechanism first and uses those files
# $ docs repair --dry-run headers <- attributes - i.e. anchor tags
# $ docs repair --dry-run images <- relative images


def find_broken_urls(md):
    """
    Examine the relative links for the MarkdownDocument object and return
    a list contain links that don't have matches on the file system.

    # Parameters

    md:MarkdownDocument
        - the document to examine

    # Return

    a list of tuples that contains the problem link and line number.

    item:
    - line number (0 based)
    - dict
        - 'full' - The full regex match - [text](link)
        - 'text' - The text portion of the markdown link
        - 'link' - The URL portion of the markdown link
        - "md_span": result.span("md"),  # tuple(start, end) <- start and end position of the match
        - "md": result.group("md"),
        - "section_span": result.span("section"),
        - "section": section attribute i.e ../file.md#id <- the id portion,

    """

    problems = []

    for rurl in md.relative_links():

        file = md.filename.parent.joinpath(rurl[1]["md"]).resolve()

        if not file.exists():
            problems.append(rurl)

    return problems


def classify_broken_urls(
    lookup=None,
    broken_urls=None,
):
    """

    Using the lookup dictionary and the list of broken urls, sort the
    broken urls for further processing. Sort them into

    - `no match` - There is no match on the file system for the URLs
    - `file match` - There are matching file names on the system
    - `suggestions` - There are no-matching file names, but some of the
                      file names are close

    # Parameters

    lookup:dict
        - A dictionary keyed by the file name mapped to a list of MarkdownDocument
        objects that have the same name but different paths.

    broken_urls:list
        - a list of tuples that contains the problem link and line number.

        - item:
            - line number (0 based)
            - dict
                - 'full' - The full regex match - [text](link)
                - 'text' - The text portion of the markdown link
                - 'link' - The URL portion of the markdown link
                - "md_span": result.span("md"),  # tuple(start, end) <- start and end position of the match
                - "md": result.group("md"),
                - "section_span": result.span("section"),
                - "section": section attribute i.e ../file.md#id <- the id portion,

    # Return

    A dictionary keyed by:

    - no_matches - no matches were found, this is a list of the broken urls
    - exact_matches - Direct matches in the file system were found, this is a tuple of the broken url and a list of MarkdownDocument objects
        - The name of the file has an exact match in the system, or a number of matches
        - multiple exact matches fount
    - exact_match - Only one exact match found
    - suggestions - Closes matches found in the file system, this is a tuple of the broken url and a list of MarkdownDocument objects
        - This may not be an ideal case or even correct.

    Each key will contain a list of tuples: (dict, list)
    - dict - this is the same dict that was in the broken_urls list
    - list - the list of Path objects that match or are similar

    """

    results = {
        "no_matches": [],
        "suggestions": [],
        "exact_match": [],
        "exact_matches": [],
    }

    for problem in broken_urls:
        line, url = problem

        key = Path(url["md"]).name

        if key in lookup:

            matches = [match for match in lookup[key]]

            if len(matches) == 1:
                results["exact_match"].append((problem, matches))

            else:
                results["exact_matches"].append((problem, matches))

        else:
            # https://docs.python.org/3/library/difflib.html#difflib.get_close_matches

            # Can we suggest anything?
            suggestions = get_close_matches(key, lookup.keys(), cutoff=0.8)

            if suggestions:
                results["suggestions"].append(
                    (problem, [match for pk in suggestions for match in lookup[pk]])
                )

            else:
                # We don't have a file match or any suggestions - a dead end :(
                results["no_matches"].append((problem, []))

    return results


def display_classified_url(results, root=None):
    """

    # Parameters

    results:list
        - A list containing a reference to a MarkdownDocument and a list of tuples
        containing line, url (dict) and the list of matches (MarkdownDocument)

    root:Path
        - The path to the root of the document folder

    """

    for item in results:
        md, problems = item
        md_relative = md.filename.relative_to(root)

        for defect, matches in problems:
            line, url = defect

            log.info(f"File: {md_relative}")
            log.info(f'Line: {line} -> `{url["full"]}`')

            for i, match in enumerate(matches, start=1):
                log.info(f"{i}. -> {match.filename.relative_to(root)}")

        log.info("")


def write_corrected_url(md=None, problems=None, root=None, dry_run=False):
    """

    # Parameters

    md:MarkdownDocument
        - The document we need to correct the URLs

    problems:list(dict, list)
        - dict - this is the same dict that was in the broken_urls list
        - list - the list of Path objects that match or are similar

    root:Path
        - The path to the root of the document folder

    """

    for defect, matches in problems:
        line, url = defect

        new_url = relative_path(
            md.filename.parent,
            matches[0].filename.parent,
        ).joinpath(matches[0].filename.name)

        new_line = md.contents[line].replace(url["md"], str(new_url))

        log.info(f"File: {md.filename.relative_to(root)}")
        log.info(f'Line: {line} - Replacing `{url["md"]}` -> `{new_url}`')

        md.contents[line] = new_line

    if dry_run:
        log.info("------DRY-RUN------")

    else:
        with md.filename.open("w", encoding="utf-8") as fo:

            for line in md.contents:
                fo.write(line)

            log.info("Changes written...")


@click.group("repair")
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the changes that would be made without actually making any.",
)
@click.pass_context
def repair(*args, **kwargs):
    """

    Repair certain things within the Markdown documents. This will
    provide tools to deal with validation issues.

    # Usage

    $ docs --config=./en/config.common.yaml repair --dry-run links


    """

    # Extract the configuration file from the click context
    config = args[0].obj["cfg"]

    config["dry_run"] = kwargs["dry_run"] if "dry_run" in kwargs else False

    # ----------------
    # Find all of the markdown files and lst files

    log.info("Searching for Markdown files...")

    config["md_files"] = search(root=config["documents.path"])

    log.info(f'{len(config["md_files"])} Markdown files were found...')
    log.info("")

    args[0].obj["cfg"] = config


@repair.command("links")
@click.pass_context
def links(*args, **kwargs):
    """

    Examine all of the Markdown documents in the configuration folder.
    Determine if there are relative lines that have a problem and attempt
    to fix them.

    - Only looks at Markdown Links of the form `[text](url)`
    - Only examines relative links
    - If it finds the correct file, and there is only one it can correct
    the link. If the link could be pointing to multiple files, it will
    not correct, but offer the suggestion of potential matches

    # Usage

    $ docs --config=./en/config.common.yaml repair --dry-run links

    """
    # Extract the configuration file from the click context
    config = args[0].obj["cfg"]

    build_start_time = datetime.now()

    # ------
    # Validate Markdown Files

    log.info("Processing Markdown File Links...")
    log.info("")

    lookup = document_lookup(config["md_files"])

    results = {
        "no_matches": [],
        "suggestions": [],
        "exact_match": [],
        "exact_matches": [],
    }

    for md in config["md_files"]:

        sorted_broken_urls = classify_broken_urls(
            lookup=lookup,
            broken_urls=find_broken_urls(md),
        )

        for key in results:

            if sorted_broken_urls[key]:
                results[key].append((md, sorted_broken_urls[key]))

    # group the output messages together so we can iterate through them and make a more
    # generic data structure

    messages = {
        "no_matches": [
            "NO MATCHES",
            "The following files had no matches or any close matches within the system.",
        ],
        "suggestions": [
            "SUGGESTIONS",
            "The following files did not have any exact matches within the system but they had some close matches.",
        ],
        "exact_matches": [
            "EXACT MATCHES",
            "The following files have multiple exact matches within the system.",
        ],
        "exact_match": [
            "EXACT MATCHES",
            "The following files have a single, exact match within the system.",
        ],
    }

    for key in (k for k in messages.keys() if k != "exact_match"):

        if results[key]:

            log.info("-" * 6)
            for msg in messages[key]:
                log.info(msg)
            log.info("")

            display_classified_url(results[key], root=config["documents.path"])

    key = k
    if results[k]:

        log.info("-" * 6)

        for msg in messages[k]:
            log.info(msg)

        log.info("")

        for item in results[k]:
            md, problems = item

            write_corrected_url(
                md,
                problems,
                root=config["documents.path"],
                dry_run=config["dry_run"],
            )

            log.info("")

        if config["dry_run"]:

            log.info(f"Exact Matches - {len(results[k])} files corrected!")
            log.info("-" * 6)

    build_end_time = datetime.now()

    log.info("")
    log.info("-" * 6)

    log.info(f"Started  - {build_start_time}")
    log.info(f"Finished - {build_end_time}")
    log.info(f"Elapsed:   {build_end_time - build_start_time}")
