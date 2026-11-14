# English Study Lab

Live website: **https://mtomanxx.github.io/englishstudylab/**

Published website files for the free English Study Lab course: B2, C1 and C2 lessons, IELTS/TOEFL/Duolingo practice, illustrated explanations and downloadable listening audio.

## Publication

The manually triggered **Publish English Study Lab** workflow reconstructs and verifies 569 website files, including 513 MP3s, before publishing the complete artifact to GitHub Pages. No secret or extra access token is required. Assembly has read-only repository access; only the final Pages job receives deployment permissions.

`site-core.tar.gz` contains the compiled app and path-adjusted data. `asset-manifest.json` records exact SHA256 hashes and sizes. `assemble-site.py` retrieves unchanged media from the currently live GitHub Pages website, verifies every file, and refuses to publish on a mismatch. All visitor-facing files and the unchanged-media source are on GitHub Pages; rebuilding does not depend on the previous host.

## Updating the website

This repository holds a compiled publication, not private source history. The editable source remains in the owner's private `english-study-lab` repository.

1. Save `asset-manifest.json` from the most recent **successful** deployment as the baseline. Do not use an untested or unpublished manifest as the baseline.
2. In the private source, run `PAGES_BASE_PATH=/englishstudylab/ npm run build:pages`.
3. Package the new build with `python3 scripts/package-pages.py --built-dir dist-pages --baseline-manifest /path/to/deployed-asset-manifest.json --output-dir /path/to/new-package`.
4. Replace `site-core.tar.gz` and `asset-manifest.json` in this publication repository, then run **Publish English Study Lab**.

The packager places every new or changed file in the core archive. Only media whose size and SHA256 match the successfully deployed baseline may be downloaded from the live site. HTML, scripts, styles, data and dotfiles stay in the core archive. This prevents a changed or newly added asset from being incorrectly fetched from an older deployment. Keep the successful deployment manifest for the next update.

Independent learning resource. Not affiliated with IELTS, ETS, Duolingo or Test-English.
