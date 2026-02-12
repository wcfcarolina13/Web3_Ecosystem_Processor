
title: Ecosystem Research Guidelines
created at: Wed Nov 19 2025 14:44:51 GMT+0000 (Coordinated Universal Time)
updated at: Tue Dec 02 2025 16:55:54 GMT+0000 (Coordinated Universal Time)
---

# Ecosystem Research Guidelines

When we say “ecosystem research” for a token/network (i.e., USDT on Tron), we’re basically doing four things:

1. **Figure out who’s in the ecosystem (primarily, supported or deployed).**
2. **Put everyone into a clean sheet.**
3. **Check who actually supports the token and how.**
4. **Sync that information back into The Grid and create follow-up work.**

Below is how that looks in practice.

***

### 1. Set the scope and create the master sheet

First we decide:

* Which ecosystem, project, network, or token we’re focusing on (e.g., USDT).
* Which networks are in scope (e.g., Tron, TON, Avalanche, BNB).

Then we **per-network sheets** (tabs in the same Sheets doc)

The network sheets are where we do the initial collection.

***

### 2. Build project lists for each network

For each network:

1. **Find projects from multiple sources**, such as:

   * Official chain/ecosystem pages
   * DefiLlama, DappRadar, Messari, CoinGecko “ecosystem” tags
   * Network docs, curated lists, and explorers
   * Recently published market maps (often found on Twitter/X, on ecosystem-focused or official network accounts)

2. **Extract all the projects/companies from these into a clean table** in the appropriate network tab of the Google Sheet with at least:

   * Project name (ProfileName)
   * Main website (URL)
   * Main X/Twitter handle (Social\_X)
   * (Optional): A secondary URL (essentially the next-best official URL for the project

3. **Clean as you go:**

   * One row per project (The initial intake may result in duplicates, legal entities, projects with direct connection to others captured in the intake, products, and pre-rebrand URLs. This is all cleaned and consolidated during the first processing run)
   * Skip obvious spam and profiles with dead URLs and no other evidence of existence (check 'skip' column to true)
   * Make sure the URL is the main site, not a tracking link or a product link (remove UTM parameters and check for product clues like an "app" extension in the address)
   * Worth repeating: During initial intake, some rows may contain products of profiles that already exist in the admin or products of projects that do NOT have profiles in the admin. In the first round of processing, always check for duplicates AND products to determine what needs to be added to the admin.

***

### 3. Standardized column names

1. Copy the templated columns to each new sheet. You can copy them from[ this project.](https://docs.google.com/spreadsheets/d/1WQSUoQQ9q_cQBZNmXcBMXVuhG2MQHVcuPoF5w6RdkfM/edit?usp=sharing) These include:

   1. \*\*Name: \*\*The name of the company/project at discovery

   2. **Suspect \<asset/network> support?:** True = You suspect the subject supports the asset/network but not necessarily proven (useful in a first-pass of the data)

   3. \*\*Skip: \*\*Mark 'True' if:

      * Subject is a person/personal account,
      * likely a scam
      * Quality does not fit TGS
      * Duplicate profile
      * No relation to Web3
      * Already in admin

   4. \*\*Added: \*\*Set to 'true" if you've added the subject to the admin. If true, either add as a new profile or a new product.

      1. Add = True when one of following is supported by the subject (these are all ongoing projects at The Grid):

      * USDT/Tether, Solana, Starknet, and General Stablecoin Adoption
      * Ensure you add all the appropriate tags to the associated profile in the admin
      * Add context to the 'Notes' column in the sheet and copy that to the 'Notes' section of the associated profile in the admin.

   5. \*\*Processed?: \*\*Processed = appended data in admin but have not completed validation

   6. \*\*Final Status: \*\*DO NOT input data anywhere in this column (If you have correctly copied the template columns, this will automatically update when you interact with the checkboxes)

   7. \*\*Notes: \*\*Document findings (e.g., bridged vs. native support + evidence). Also good practice to add admin URLs here once they exist

2. \*\*AI Processing columns: \*\*These are columns used to process the raw data through LLMs and automatically add to the sheet (see the section on AI processing). They're optional if you are not using LLMs to assist in your research. They include:
   1. \*\*Best URL: \*\*Use this column to run the "Process URLs with field selection" script. Researchers must still confirm it is a valid PROFILE URL (to catch invalid URLs or product URLs)
   2. \*\*Best social: \*\*Best official social URL of the subject, typically X or LinkedIn. Useful for confirming the project's status and main URL quickly.
   3. \*\*Secondary URL: \*\*Next-best official source for the subject. Useful for issues like broken links, rebrands, and confirming that we've got the correct subject.

3. \*\*Additional columns can be added depending on the project. \*\*For example, for the USDT ecosystem research project, we include:
   1. \*\*Web3 but no stablecoin: \*\*Has a Web3 connection, but no proof that profile supports any stablecoin (e.g., a law firm)
   2. **General Stablecoin Adoption:** True if = Supports at least one stablecoin but not USDT (e.g., USDC)

4. **Run the "Process URLs with field selection" script** (Extensions → The Grid Supporter → Process URLs with Field Selection → Column containing URLs: <choose your source column> → Rows to process: <skip headers and choose target range> → Select data fields to retrieve \<Generally, you'll only need 'Matched URL' and 'Profile Name'> → Process URLs
   1. It'll take a while, so give it a moment to finish processing
   2. Make sure it hasn't overwritten any columns to ensure you've properly appended the sheet
   3. ⚠️ Use the results as a guide rather than an absolute; It's not perfect and sometimes misses near-matches and URLs that may have been changed officially, and it will not identify rows that contain only products of existing profiles.

⚠️ When running "Process URLs with field selection," remember that the sheet will be appended to the right of the selected source column, overwriting all columns that come after that position. Therefore, it's best to adjust the source column's position to the end of your sheet after your initial LLM work is done. That way, the script will only append to empty or new columns and not erase your work.

1. **Follow-up**
   1. Regularly update the main Linear ticket of the ecosystem research project and any related subtasks with a short progress report as you make your way through the sheet(s).
2. \*\*Validation: \*\*
   1. Researchers must check the "Added" column for "Final Status" on the row to switch to "Added, not validated"
   2. Researchers must check the "Processed?" column to "true" to indicate that the profile is ready for validation in the admin.
   3. During validation, researchers can filter the list to show only rows with both "Added" and "Processed?" that are set to 'true' for a clear view on what needs to be validated
3. **Additional tips**
   1. It's useful to highlight rows that the researcher believes needs a follow-up with the team. Beige fill is sufficient. Remember that if you use custom views, it may hide these rows
   2. In the sheet, you can convert pasted csv-friendly LLM outputs into columns via: Data → 'Split text to columns'

***

# LLM Research

Using LLMs to assist with the initial data intake and research has proven to be very useful. Manage your expectations on speed, and results vary depending on which LLM tool you are using.

The general idea is with an LLM that has internet access, you can ask it to check an ecosystem page and map all the subjects therein to a main URL, Secondary URL, and main social URL. That is the bare minimum to work with the columns outlined earlier, but you can extend it to also do preliminary research on product or asset support, for example.

The following is a prompt you can give an LLM.

## LLM Ecosystem Research Prompts

📜 Alter these prompts to fit the ecosystem project you are working on.

### Top-level prompt example

```javascript
Search and identify some of the most prominent ecosystem pages for the Avalanche, Tron, and BNB Smart Chain ecosystems.
```

Example chat where that prompt was used (there's a lot happening, so just focus on the early responses): https://chatgpt.com/share/68eceae6-6408-8006-b5cc-f3db6f50294d

Getting the results you want with spreadsheets and csv-friendly responses that won't bork your sheet when pasted in and converted to columns is not exactly straightforward. Sometimes it can feel like a random walk, but with patience and clever prompting, you can get the results you need. See the following chat for an example of how ChatGPT was used to scrape various market maps and ecosystem pages and compare its findings to existing data:

https://chatgpt.com/share/691df49a-ab4c-8006-b748-51cfa2ef5d94

Be sure that the column names you provide the LLM match the same order in the sheet, otherwise it will be a pain to paste in the output and split the text to columns.

Remember, if you've hidden any rows or columns, it may bork the result.

Also, sometimes formatting issues like additional commas can bork the result (it may cause the data to shift into adjacent columns, for example).

Don't expect one-shots or perfect output. Use AI to assist you; but if you have not developed a good system and find it too time-consuming, you'll have to proceed manually.

The above results were with ChatGPT. At The Grid, we usually use Claude, which has context window issues. Something to be aware of.

***

## Ecosystem Research Instruction Prompt

```plaintext
PROMPT PACK — Ecosystem Research Intake (Resource-by-Resource, CSV edited iteratively)

ROLE
You are assisting with ecosystem research intake for:
- Target asset/topic: {ASSET} (e.g., USDT)
- Target network: {CHAIN} (e.g., Tron, TON)
We are in the INITIAL INTAKE PHASE: building clean project lists per network + early hints (suspect flags). We are NOT doing final validation yet.

OPERATING MODE
- Two phases:
  PHASE 1 = Ecosystem resource gathering (discover sources only; no CSV yet)
  PHASE 2 = Process resources one at a time; build the CSV at resource #1, then EDIT/APPEND it per resource thereafter.
- Only process ONE resource per turn.
- Before starting the NEXT resource, ask: “Proceed to next resource?” and wait for approval.
- At the end of each processed resource, report: “Resources remaining: X”.

================================================================================
PHASE 1 — Ecosystem Resource Gathering (NO CSV IN THIS PHASE)
INPUT I WILL PROVIDE:
- {CHAIN} and {ASSET}
TASK:
1) Produce a list called “Resource Results” containing the most prominent ecosystem sources for {CHAIN}, including:
   - Official chain/ecosystem pages (foundation, docs, ecosystem directory)
   - Aggregators (DefiLlama, DappRadar, Messari landscape, CoinGecko category, CoinMarketCap ecosystem)
   - Explorers with curated dapp/token lists (if any)
   - Recent market maps (often on X)
2) For each resource result, output:
   - Resource_Name
   - Resource_Type (one of: Official Directory | Aggregator Directory | Token Ecosystem List | Market Map/Landscape | Explorer Directory | Misc Curated List)
   - URL
   - Why_Useful (1 sentence)
3) Do not begin extracting projects yet.

STOP after “Resource Results” list.

================================================================================
PHASE 2 — Per-Resource Processing (BUILD/EDIT CSV)
INPUTS I WILL PROVIDE EACH TURN:
- One target resource URL or PDF/text export: {RESOURCE}
- My current master CSV (may be empty for the first resource): {MASTER_CSV}
- Optional expected counts (e.g., “should be 142 projects”)

GLOBAL INTAKE + CLEANING RULES (apply to all resources)
A) Unit of row = Profile (project/company), not a product.
   - If a listed item is clearly a product of an existing profile: keep ONE row for the parent, mention product in Notes.
B) De-dupe:
   - Case-insensitive name match
   - Domain match (same root domain treated as match)
   - Light normalization: strip punctuation, collapse spaces
C) URL hygiene:
   - Use canonical homepage when possible.
   - Remove UTM/tracking params.
   - Avoid using pure “app.” pages as the main URL unless that is the primary official entrypoint.
D) Skip handling:
   - Do NOT delete questionable entries; set Skip = TRUE and explain briefly in Notes.
   - Skip TRUE for: personal accounts, obvious scam/spam, dead URL with no other evidence, non-Web3 unrelated.
E) CSV safety:
   - Output must be CSV-friendly with consistent column count.
   - Keep Notes short; avoid commas unless quoted.
F) Delta logic:
   - We do not output your master list.
   - We output only NEW additions not already in the master (after normalization).
G) Suspect flags for this intake phase:
   - “Suspect USDT support?”: TRUE only if the resource itself strongly suggests stablecoin/USDT usage; otherwise blank.
   - “Web3 but no stablecoin”: TRUE if clearly Web3 but no stablecoin evidence in this intake step (optional; otherwise blank).
   - “General Stablecoin Adoption”: TRUE if clearly supports stablecoins but not specifically USDT (optional; otherwise blank).
H) Chain column:
   - Always set Chain = {CHAIN} for every row in this run.

CSV COLUMN ORDER (27 columns — MUST MATCH EXACTLY; keep non-intake columns blank)
Project Name,
Suspect USDT support?,
Skip,
Added,
Web3 but no stablecoin,
General Stablecoin Adoption,
To be Added,
Processed?,
In Admin,
TG/TON appstore (no main URL),
Final Status,
Website,
X Link,
X Handle,
Telegram,
Category,
Release Date,
Product Status,
The Grid Status,
Profile Name,
Root ID,
Matched URL,
Matched via,
Chain,
Source,
Notes,
Evidence & Source URLs

- For intake: populate Project Name, Skip, Notes, Website, X Link, X Handle, Category, Chain, Source.
- Leave everything else blank unless explicitly asked.

================================================================================
RESOURCE ROUTER (IF-THEN SELECTION)
Given {RESOURCE}, choose the closest matching instruction block below.
- If the resource is not an exact match, choose the best-fitting block by type (directory vs token list vs PDF vs landscape map).

After selecting the block, you must:
1) Extract ALL items from the resource (subject to skip rules).
2) Create/Update the running CSV:
   - If this is the first processed resource: output the CSV with headers + rows (delta-only vs master if master provided).
   - If CSV already exists: output ONLY the new rows to append (delta-only), using the same column order.
3) Provide counts and “Resources remaining: X”.
4) Ask permission to continue: “Proceed to next resource?”

--------------------------------------------------------------------------------
BLOCK 1 — CMC / CoinGecko (Token Ecosystem List)
Use when:
- URL contains coinmarketcap.com/view/ OR coingecko.com/.../categories/... OR it is clearly a token ecosystem/category list.

Special rules:
1) These lists are token-centric; map to the project/company only if obvious from official site branding.
2) Apply any provided filters (e.g., skip memecoins; market cap threshold) IF the user included them for this run.
3) Best URL:
   - Prefer official website from the token’s page.
   - If none: use the best official docs/GitHub; if still none, leave Best URL blank and add Notes.
4) Best social:
   - Prefer official X/Twitter from the token/project page; otherwise blank.

Output requirements:
- Delta-only rows (net-new vs master).
- Counts: total listed, duplicates removed, skipped marked, exported rows.

--------------------------------------------------------------------------------
BLOCK 2 — Aggregator Directory (DefiLlama / DappRadar / “Top dapps” style pages)
Use when:
- DefiLlama chain page, DappRadar chain filter, Rayo/thedapplist, dapp.expert, etc.

Special rules:
1) Treat each listed entry as a potential profile.
2) If only aggregator links exist:
   - Put aggregator link as Secondary URL (not Best URL) unless no official link exists anywhere.
3) Suspect flags:
   - “Web3 but no stablecoin” may be set TRUE when clearly Web3 but no stable/stablecoin hints.

Output requirements:
- Delta-only rows.
- Counts: extracted, deduped, already in master, exported.

--------------------------------------------------------------------------------
BLOCK 3 — Alchemy Ecosystem Directory (Paginated)
Use when:
- alchemy.com/dapps/ecosystem/{chain} or similar; pages/size parameters exist.

Special rules:
1) Exhaustive: follow pagination until complete.
2) If client-rendering prevents extraction:
   - Request a PDF/text export and stop; do not guess.
3) Mark Chain = {CHAIN} for all rows.

Output requirements:
- Delta-only rows.
- Counts: pages processed, extracted, deduped, already in master, exported.

--------------------------------------------------------------------------------
BLOCK 4 — Messari Landscape / Market Map (Image/PDF/Text export)
Use when:
- Messari landscape portal or a map export (image/PDF/text).

Special rules:
1) De-dupe across categories: one row per unique project.
2) Accept that some entries are infra vendors; do not skip solely for being “offchain” unless clearly unrelated.
3) If OCR noise: normalize gently; record any serious ambiguity in Notes.

Output requirements:
- Delta-only rows.
- Counts: unique projects, multi-category duplicates found, exported.

--------------------------------------------------------------------------------
BLOCK 5 — Official Ecosystem Directory (Foundation/Docs “Ecosystem” page)
Use when:
- ton.app, official ecosystem listings, foundation ecosystem pages, docs directories.

Special rules:
1) Prefer the official homepage as Best URL.
2) Secondary URL can be docs page or app link if it’s official.
3) Best social: official X if discoverable; otherwise blank.

Output requirements:
- Delta-only rows.
- Counts: extracted, deduped, already in master, exported.

--------------------------------------------------------------------------------
BLOCK 6 — Explorer Directory Lists (Tonviewer/Tronscan/OKLink, etc.)
Use when:
- Explorer has a curated dapp/token list.

Special rules:
1) Treat explorer listing as evidence the project exists on {CHAIN}; mention in Notes.
2) Use official website as Best URL; explorer token/account page goes in Secondary URL if useful.

Output requirements:
- Delta-only rows.
- Counts: extracted, deduped, exported.

--------------------------------------------------------------------------------
BLOCK 7 — PDF/Text Dump (Any Source)
Use when:
- You receive a PDF export or copied text.

Special rules:
1) Be exhaustive. If expected count provided, verify it; if mismatch, report your count and why (headers/duplicates/OCR).
2) Do not invent URLs; if missing, leave blank and note.

Output requirements:
- Delta-only rows.
- Counts: extracted, deduped, exported.

================================================================================
END-OF-RESOURCE TURN OUTPUT TEMPLATE
After processing the resource, output in this exact structure:

1) “Chosen instruction block: {BLOCK_NAME}”
2) “Delta rows to append (CSV):”
   - If first resource: include header + rows
   - Else: rows only (no header), still in the same column order
3) “Counts: extracted=X; deduped=Y; skipped-marked=Z; already-in-master=K; exported=E”
4) “Resources remaining: {N}”
5) “Proceed to next resource?”

================================================================================
START COMMAND (WHAT I WILL TYPE TO INITIATE WORK)
"PHASE 1: Gather ecosystem resources for {CHAIN} / {ASSET}."
Then I will paste the Resource Results and tell you which resource to process first.

```

---

# Automated Ecosystem Research Tools

## Chrome Extension Scraper

A Chrome extension has been built for scraping data from complex JavaScript/React ecosystem directories. Located at:
`/Ecosystem Research/ecosystem-scraper-extension/`

### Supported Sites
| Site | Method | Data Available |
|------|--------|----------------|
| AptoFolio | Global variable | Names, categories, 90+ Twitter handles |
| DefiLlama | Public API | Names, URLs, Twitter, TVL, categories |
| DappRadar | DOM scraping | Names, slugs, categories |
| CoinGecko | DOM scraping | Coin names, slugs |

### Installation
1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" → select the `ecosystem-scraper-extension` folder

---

## Automated Comparison & Merge Process

Python scripts for comparing scraped data against existing CSV and merging new projects:

### Scripts Location
`/Ecosystem Research/scripts/`

### Workflow

1. **Scrape data** from sources (DefiLlama API, DappRadar DOM, etc.)

2. **Compare with existing CSV** using `compare_and_merge.py`:
   - Normalizes names for comparison (removes suffixes like "Protocol", "Finance", "V2")
   - Uses string similarity matching (>80% threshold)
   - Identifies duplicates that might need enhancement
   - Identifies new projects to add

3. **Review comparison report** in `comparison_report.txt`:
   - Shows duplicates with match scores
   - Lists new projects with full details

4. **Merge new projects** using `merge_new_projects.py`:
   - Appends only genuinely new entries
   - Maintains CSV format consistency
   - Sets appropriate columns (Suspect USDT support?, Web3 but no stablecoin, etc.)

### Key Functions

```python
def normalize_name(name):
    """Normalize for comparison - removes common suffixes, lowercase, alphanumeric only"""

def find_match(name, existing_names):
    """Find best match using normalization + similarity scoring"""

def generate_new_csv_rows(new_projects):
    """Generate properly formatted CSV rows for new entries"""
```

### Example Usage

```bash
# Compare DefiLlama data
cd /Ecosystem Research
python3 scripts/compare_and_merge.py

# Merge new projects
python3 scripts/merge_new_projects.py

# Compare DappRadar data
python3 scripts/compare_dappradar.py
python3 scripts/merge_dappradar.py
```

### Duplicate Handling

The comparison process flags duplicates that may need data enhancement:
- **100% match**: Exact name match after normalization
- **90% match**: One name contains the other
- **>80% match**: High string similarity

For duplicates, review if the new source has better:
- URLs (more canonical)
- Twitter handles
- TVL data
- Descriptions

---

## Data Source Priority

When merging from multiple sources, prioritize data quality:

1. **DefiLlama API** - Best for DeFi protocols (has TVL, URLs, Twitter, descriptions)
2. **DappRadar** - Good for games and broader dapp coverage
3. **AptoFolio** - Community-curated, good for newer projects
4. **CoinGecko** - Good for token-based projects

          