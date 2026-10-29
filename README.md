# Research priority study

This study compares research responses across neutral, growth, and resilience
conditions: six repetitions per condition for each of two providers (36 runs).

- `code/run_study.py`: submits and collects the study through provider batch APIs.
- `code/create_review_workbook.py`: builds the manual review workbook from saved responses.
- `data/official_v1/`: collection schedule, provider batch records, and run results.
  Each run includes requests, raw responses, metadata, a final report, and usage.
- `data/official_v1/official_collection_review.xlsx`: manual review workbook.
  See [review instructions](data/official_v1/MANUAL_REVIEW_README.md).

To run a new collection, install `openai` and `anthropic`, set the
`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` environment variables, and choose a new
`COLLECTION_NAME` in `code/run_study.py`. Then run:

```sh
python3 code/run_study.py
```

Confirm with `RUN COLLECTION` to submit paid API requests. Batch completion can
take hours. The script refuses to overwrite an existing collection directory.
