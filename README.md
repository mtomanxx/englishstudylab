# English Study Lab

Published website files for the free English Study Lab course: B2, C1 and C2 lessons, IELTS/TOEFL/Duolingo practice, illustrated explanations and downloadable listening audio.

## Publication

The manually triggered **Publish English Study Lab** workflow reconstructs and verifies 569 website files, including 513 MP3s, before publishing the complete artifact to GitHub Pages. No secret or extra access token is required. Assembly has read-only repository access; only the final Pages job receives deployment permissions.

`site-core.tar.gz` contains the compiled app and path-adjusted data. `asset-manifest.json` records exact SHA256 hashes and sizes; `assemble-site.py` retrieves unchanged public media and refuses to publish on a mismatch. All visitor-facing files are served from GitHub Pages after deployment.

This repository holds a compiled publication, not private source history. The editable source remains in the owner's private `english-study-lab` repository. Rebuild there with `npm run build:pages`, using `PAGES_BASE_PATH=/englishstudylab/`, then replace the delivery package and rerun the publication workflow.

Independent learning resource. Not affiliated with IELTS, ETS, Duolingo or Test-English.
