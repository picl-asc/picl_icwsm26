# Comprehensive TikTok Data Collection for Computational Social Science

**ICWSM 2026 Tutorial · Hands-on notebook**

Gayoung Jeon · Cameron Moy · Deen Freelon
Annenberg School for Communication, University of Pennsylvania

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/License-BSD--3--Clause-green) ![Status](https://img.shields.io/badge/Status-Tutorial%20Demo-orange)

This repository contains the hands-on materials for our ICWSM 2026 tutorial on collecting TikTok data for computational social science research. The notebook walks through three independent data-collection tools — the official **TikTok Research API**, **Apify** (a commercial cloud scraper), and **pyktok_2026** (an open-source browser-based scraper shipped in this repository) — and shows how to think critically about what each one returns. Our stress-testing research finds these tools frequently produce strikingly different results for identical queries, so understanding the differences is part of the methodology, not a side note.

> **Status:** the `pyktok_2026` build included here is the **no-login demo subset** (Hashtag, Keyword, Sound). The full revision — covering user, comments, related videos, trending, and playlists — is in active development and will land in the public [Pyktok](https://github.com/dfreelon/pyktok) release. All code is provided **as-is**; you use it at your own risk.

---

## Table of contents

- [Quick start](#quick-start)
- [What's in this repository](#whats-in-this-repository)
- [Setup](#setup)
- [Credentials](#credentials)
- [Tutorial structure](#tutorial-structure)
- [Tool comparison](#tool-comparison)
- [API quota limits (Section 2-1)](#api-quota-limits-section-2-1)
- [What this build of pyktok_2026 exposes](#what-this-build-of-pyktok_2026-exposes)
- [Output file naming](#output-file-naming)
- [Modifying inputs](#modifying-inputs)
- [A note on data quality](#a-note-on-data-quality)
- [License](#license)
- [Citation](#citation)
- [Contact and issues](#contact-and-issues)

---

## Quick start

```bash
git clone https://github.com/picl-asc/picl_icwsm26.git
cd picl_icwsm26

python3 -m venv tiktok-env
source tiktok-env/bin/activate          # Windows: tiktok-env\Scripts\activate

cp credential.env.example credential.env    # fill in your tokens — see below

jupyter notebook tt_tutorial.ipynb
```

The first three cells of the notebook install all Python dependencies and the bundled Chromium browser. Open the notebook and Run All — or run section by section. Each section is self-contained.

If you don't have Git, the **Code → Download ZIP** button on the GitHub page does the same thing.

---

## What's in this repository

```
tt_tutorial.ipynb            the main hands-on notebook
tt_tutorial.html             rendered HTML version (for previewing without Python)
pyktok_2026/                 the open-source scraper used in Section 2-3
pyproject.toml               packaging metadata for pyktok_2026
sample_data/                 example output files used by Section 3 (analysis)
credential.env.example       template for your secrets file
README.md                    this file
```

`credential.env` is **not** committed. You create it locally from the template; it should be listed in your local `.gitignore` along with any output CSVs.

---

## Setup

Requires **Python 3.10 or later**. A virtual environment is strongly recommended:

```bash
python3 -m venv tiktok-env
source tiktok-env/bin/activate          # Windows: tiktok-env\Scripts\activate
```

The notebook installs everything in its first three cells. If you would rather install upfront from the shell:

```bash
pip install TikTokResearchApi python-dotenv pandas requests tqdm
pip install apify-client
pip install -e .                        # installs pyktok_2026 from this folder
playwright install chromium             # downloads the headless browser
```

---

## Credentials

Two of the three tools need API credentials. Copy the template and fill in your values:

```bash
cp credential.env.example credential.env
```

Then edit `credential.env`:

```dotenv
# TikTok Research API (Section 2-1)
CLIENT_KEY=your_client_key_here
CLIENT_SECRET=your_client_secret_here

# Apify (Section 2-2)
APIFY_API_TOKEN=your_apify_token_here
```

**Where to obtain each:**

| Tool | Where | Notes |
|---|---|---|
| **TikTok Research API** | [developers.tiktok.com/products/research-api](https://developers.tiktok.com/products/research-api/) | Academic application; review takes a few weeks. Apply well in advance. |
| **Apify** | [apify.com](https://apify.com) → Settings → Integrations → API Token | Free account; ~$5 in credits to start. |
| **pyktok_2026** | — | No credentials required. |

If you don't have Research API access yet, Sections 2-2 and 2-3 still work standalone.

---

## Tutorial structure

Open `tt_tutorial.ipynb` and work through it in order, or jump to whichever tool you have access to. Each section is independent.

| Section | Tool | Endpoints covered |
|---|---|---|
| **1. Setup** | — | Install packages, set up credentials |
| **2-1. Research API** | TikTok Research API | User, User Info, Keyword, Hashtag, Comments |
| **2-2. Apify** | Apify (commercial) | User, Keyword, Hashtag, Comments, Related Videos |
| **2-3. pyktok_2026** | Open-source scraper (no login) | Hashtag, Keyword, Sound |
| **3. Sample analysis** | pandas / matplotlib | Aggregations and exploratory plots on the collected data |

---

## Tool comparison

| | Research API | Apify | pyktok_2026 |
|---|---|---|---|
| **Access** | Academic application | Free tier (~$5 credit) | Free, open source |
| **Cost** | Free | ~$0.25–$1.00 / 1,000 results | Free |
| **Endpoints (this build)** | User, Keyword, Hashtag, Comments | User, Keyword, Hashtag, Comments, Related | Hashtag, Keyword, Sound |
| **Data source** | Back-end API | Front-end cloud scrape | Front-end browser scrape (headless Chromium) |
| **Daily limits** | 1,000 calls/day | Credit-based | TikTok rate limits apply |
| **Auth required** | OAuth (`CLIENT_KEY`, `CLIENT_SECRET`) | API token | None |

---

## API quota limits (Section 2-1)

The Research API gives you **1,000 calls per day**, shared across all endpoints:

| Endpoint | Max per call | Daily call budget | Practical max/day |
|---|---|---|---|
| Video (user / keyword / hashtag) | 100 videos | shared 1,000 | ~100,000 videos |
| Comments | 100 comments | shared 1,000 | ~100,000 comments |

If you run a keyword query that uses 500 calls, you have 500 left for everything else that day. Plan accordingly.

---

## What this build of `pyktok_2026` exposes

Section 2-3 uses the **no-login demo subset** that ships in this repository. The public surface is intentionally narrow — only endpoints that work without a TikTok session cookie:

```python
pyk.specify_browser   pyk.close          pyk.set_verbosity   pyk.setup
pyk.get_tiktok_json       # parse one video's page JSON (use to find hashtags / sound IDs)
pyk.get_hashtag_info      # challenge metadata
pyk.get_hashtag_videos    # paginated videos for a hashtag
pyk.search_videos         # paginated videos for a search keyword
pyk.get_sound_info        # music metadata
pyk.get_sound_videos      # paginated videos using a sound
pyk.safe                  # nested-dict access helper
```

The login-required endpoints (user archives, comments, related videos, trending feeds, playlists) are part of the full revision in development. They will be merged into the public [Pyktok](https://github.com/dfreelon/pyktok) release.

---

## Output file naming

All CSVs follow the same convention so you can tell at a glance what tool collected what, when:

```
{tool}_{endpoint}_{target}_{YYYYMMDD}T{HHMMSS}.csv
```

Examples:

```
api_user_apnews_20240515T143022.csv
api_keyword_climate_change_20240515T160003.csv
apify_hashtag_booktok_20240515T172301.csv
pyktok_sound_7099827699635505963_20240515T191205.csv
```

---

## Modifying inputs

Every line in the notebook you would reasonably modify is marked with an ALL-CAPS comment immediately above it, for example:

```python
# CHANGE USERNAME TO YOUR OWN TARGET TIKTOK ACCOUNT (no '@')
username = "apnews"

# CHANGE START_DATE TO YOUR EARLIEST DATE (YYYYMMDD) — both start_date and end_date are REQUIRED by the API
start_date = "20240101"
```

The marked lines cover all the inputs that matter — usernames, hashtags, keywords, sound IDs, date ranges, target counts. For a basic run you should not need to edit anything outside those marked lines.


---

## License

BSD-3-Clause. Materials are open-access and free of copyright restrictions. See the `LICENSE` file when added at the repo root.

---

## Citation


If you use these materials, please cite:

> Jeon, G., Moy, C., & Freelon, D. (2026). *Comprehensive TikTok Data Collection for Computational Social Science.* Proceedings of the Workshop at the International AAAI Conference on Web and Social Media (ICWSM).

BibTeX:

```bibtex
@inproceedings{JeonMoyFreelon2026,
  author    = {Jeon, G. and Moy, C. and Freelon, D.},
  title     = {{Comprehensive TikTok Data Collection for Computational Social Science}},
  booktitle = {Proceedings of the Workshop at the International AAAI Conference on Web and Social Media (ICWSM)},
  year      = {2026},
  month     = {05},
  address   = {Los Angeles, CA, USA}
}
```
---

##Contact and Issues

Found a bug, broken endpoint, or unclear instruction? Please open a GitHub issue on the repository. That is the fastest way to get a fix.

For methodological questions, contact one of the authors:

| Author | Email |
|---|---|
| Gayoung Jeon | gjeon@upenn.edu |
| Cameron Moy | moycam@upenn.edu |
| Deen Freelon | dfreelon@upenn.edu |
