# Manual review workbook

Open `official_collection_review.xlsx`. It includes the 36 official runs only; pilots are excluded. All sheets connect through `run_id`. Freeze panes and filters are enabled. Yellow columns are editable review fields. No factual claims or source choices have been corrected.

Start with `Runs` and `Reports`, then review `Queries`, `Returned_Sources`, `Citations`, and `Report_Units`. `Tool_Actions` preserves browsing actions; `Usage` preserves reported usage by API round. Mark reviewed runs/reports using Pending/Reviewed. Binary fields accept 0/1; navigational flags are deliberately blank until you apply a consistent definition.

## Provisional extraction rules

- Report text in `Reports` is copied exactly from `final_report.txt`. Long cells may not display completely at Excel's maximum row height; use the formula bar or cell edit mode to inspect the full text.
- Report-unit splitting is provisional. Adjacent Claude text blocks are rejoined for unit extraction to avoid splitting sentences at citation-block boundaries; tool-separated announcements remain separate. The Reports sheet remains unchanged. Line-based headings, bullets, and table rows are retained; prose is provisionally split at sentence punctuation. Review abbreviations, numbered text, multiline prose, and compound bullets.
- Headings and separator lines are excluded. Table rows are included in the sheet but marked `include_unit = 0` until you freeze a consistent table rule. Other provisional units start with `include_unit = 1`. All `split_reviewed` fields start at 0.
- OpenAI citation positions are preserved exactly as returned (relative to the provider output text block). Claude citation excerpts are source evidence, not necessarily the report's wording. Unavailable fields remain blank.
- Citation-to-unit mappings use OpenAI annotation offsets or Claude's attributed text block. All mappings require review (`mapping_reviewed = 0`). A citation spanning several units lists their IDs separated by semicolons. Unit citation counts count overlaps; do not sum these counts to obtain the study's total citation occurrences.
- Each OpenAI query in a multi-query search gets its own row. Returned sources are linked to a query only if the action contains one query; multi-query source lists have blank query IDs. Claude result records link through tool-use IDs. OpenAI returned source lists are the sources exposed by the API, not guaranteed to be complete search-engine result lists. Titles are blank when unavailable.
- URLs are normalized only by lowercasing scheme/host and removing fragments and known tracking parameters (`utm_*`, `gclid`, `fbclid`, `msclkid`). Functional query parameters and path case are retained. `cited_anywhere` compares normalized URLs within the same run.
- Word counts use whitespace-separated tokens from the exact saved report, including links and announcements. These differ from the earlier descriptive analysis's URL-stripped word counts.
- Missing usage fields remain blank. Claude total tokens are not synthesized; caching/thinking fields map from provider-reported values. Blank search request counts are not zero.

Workbook creation uses `code/create_review_workbook.py` and makes no API calls. Regenerating the workbook replaces it, including manual edits; save an edited copy under a different filename before rerunning the script.
