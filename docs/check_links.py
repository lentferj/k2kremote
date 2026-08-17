#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  k2kremote contributors
#
# This file is part of k2kremote.  Original work.  GPL-2.0-or-later.

"""Check every link in the project's Markdown: anchors, files, and URLs.

    .venv/bin/python docs/check_links.py            # everything
    .venv/bin/python docs/check_links.py --offline  # skip URLs (what CI runs)

Exists because this project keeps finding its documentation out of date: paths
that moved when the macro editor became its own package, an anchor that changed
when a heading was reworded, images renamed. Those are all mechanically checkable,
and none of them were being checked.

`--offline` skips the network so CI is deterministic — a URL check that fails on
someone else's rate limit teaches people to ignore the job.

Three classes, three different ways to be wrong:

* **in-document anchors** (`#section`) — must match a heading in the same file,
  under GitHub's slug rules (lowercase, punctuation dropped, spaces to hyphens,
  duplicates suffixed -1, -2...).
* **relative paths** (`docs/FOO.md`, `docs/img/x.png`) — resolved relative to the
  file that contains the link, not to the repo root; and if they carry an anchor,
  that anchor is checked against the target file's headings too.
* **absolute URLs** — checked over the network when there is one, and reported as
  unverified rather than passed when there is not.
"""
import pathlib
import re
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent

# The label may itself contain a bracketed image — a badge is
# [![alt](img)](target) — so the label pattern has to allow nested [ ].
# Without this the badge's click target is silently never checked.
INLINE = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
HREF = re.compile(r'<a[^>]+href="([^"]+)"')
# Markdown images, matched separately: with a badge the outer link and the
# inner image are two different URLs, and one pattern only ever finds one of
# them. Checking the click target while skipping the image (or vice versa) is
# worse than useless — it reports success over an unchecked link.
IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.M)
FENCE = re.compile(r"```.*?```", re.S)


def slug(text: str) -> str:
    """GitHub's heading slug."""
    text = re.sub(r"<[^>]+>", "", text)          # inline HTML
    text = re.sub(r"[`*_~]", "", text)           # emphasis / code marks
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)         # drop punctuation, incl. em dash
    return re.sub(r"\s", "-", text)   # NOT \s+ : runs are not collapsed


def anchors_of(path: pathlib.Path) -> set:
    if not path.exists() or path.suffix.lower() != ".md":
        return set()
    body = FENCE.sub("", path.read_text(encoding="utf-8", errors="replace"))
    seen, out = {}, set()
    for _, title in HEADING.findall(body):
        base = slug(title)
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    # explicit anchors, e.g. <a name="x"> or id="x"
    out |= set(re.findall(r'<a[^>]+name="([^"]+)"', body))
    out |= set(re.findall(r'id="([^"]+)"', body))
    return out


def links_of(path: pathlib.Path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = FENCE.sub("", raw)                    # never lint inside code fences
    for _, target in INLINE.findall(body):
        yield target
    for _, target in IMAGE.findall(body):
        yield target
    for target in IMG_SRC.findall(body) + HREF.findall(body):
        yield target


def have_network() -> bool:
    """True when URLs can be checked. --offline is a choice, not a failure."""
    try:
        urllib.request.urlopen("https://github.com", timeout=6)
        return True
    except Exception:
        return False


def main() -> int:
    skip = {".git", ".venv", "build", "dist", "node_modules", "__pycache__",
            ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    md = sorted(p for p in REPO.rglob("*.md")
                if not (skip & set(p.parts)) and "egg-info" not in str(p))
    offline = "--offline" in sys.argv
    online = False if offline else have_network()
    if offline:
        print("network: skipped (--offline); URLs not checked")
    else:
        print(f"network: {'available' if online else 'UNREACHABLE — URLs not checked'}")
    print(f"checking {len(md)} markdown files\n")

    urls, problems, outside = {}, [], []
    counts = {"anchor": 0, "file": 0, "url": 0}
    for path in md:
        own = anchors_of(path)
        for target in links_of(path):
            if target.startswith(("http://", "https://")):
                counts["url"] += 1
                urls.setdefault(target, []).append(path)
            elif target.startswith("#"):
                counts["anchor"] += 1
                if target[1:] not in own:
                    problems.append((path, target, "no such heading in this file"))
            elif target.startswith("mailto:"):
                continue
            else:
                counts["file"] += 1
                file_part, _, frag = target.partition("#")
                dest = (path.parent / file_part).resolve()
                # A link that leaves the repository cannot be verified from a
                # checkout: docs/MAC_FORMAT.md points at the sibling mpc2emu
                # project, which exists on the author's machine and on no CI
                # runner. It passed locally for the wrong reason and then failed
                # every job. Reported, not failed — an unverifiable link is not a
                # broken one, and treating it as broken makes the check unusable
                # exactly where it runs unattended.
                try:
                    dest.relative_to(REPO)
                    inside = True
                except ValueError:
                    inside = False
                if not inside:
                    outside.append((path, target, dest.exists()))
                elif not dest.exists():
                    problems.append((path, target, "file does not exist"))
                elif frag and frag not in anchors_of(dest):
                    problems.append((path, target,
                                     f"file exists, no anchor #{frag} in it"))

    for url, where in sorted(urls.items()):
        if not online:
            continue
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "link-check"})
            code = urllib.request.urlopen(req, timeout=15).status
            if code >= 400:
                problems.append((where[0], url, f"HTTP {code}"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 405, 429):      # bot-blocked / HEAD unsupported
                print(f"  ? {url}  HTTP {exc.code} (likely bot protection)")
            else:
                problems.append((where[0], url, f"HTTP {exc.code}"))
        except Exception as exc:
            problems.append((where[0], url, f"{type(exc).__name__}: {exc}"))

    print(f"\nlinks checked: {counts['anchor']} anchors, {counts['file']} files, "
          f"{counts['url']} urls ({len(urls)} distinct)")
    for path, target, here in outside:
        print(f"  ? {path.relative_to(REPO)}: {target}  -> outside the repo, "
              f"{'present here' if here else 'not present here'}; not checked")
    if not problems:
        print("no broken links")
        return 0
    print(f"\n{len(problems)} PROBLEM(S):")
    for path, target, why in problems:
        print(f"  {path.relative_to(REPO)}: {target}\n      -> {why}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
