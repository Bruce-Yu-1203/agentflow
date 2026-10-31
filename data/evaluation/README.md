# Support Evaluation Dataset

`support_train.json`, `support_validation.json`, and `support_test.json` are version 1 of a balanced English customer-support benchmark. The utterances and conversations are realistic synthetic examples written for this project. They contain no real customer records or credentials. Review and extend the labels with a domain expert before using results as production-quality evidence.

## Contents

| Split | Intent cases | Dialogue cases | RAG cases |
| --- | ---: | ---: | ---: |
| Train | 190 | 0 | 0 |
| Validation | 95 | 10 | 30 |
| Test | 95 | 10 | 30 |

The intent set covers all 19 runtime labels with 20 cases per label: 10 train, 5 validation, and 5 test. Each intent request stays within the API limit of 200 cases. The RAG cases identify the relevant document IDs from `data/knowledge/demo_knowledge.json`; each validation and test split has five queries per document. Dialogue cases cover multi-turn context, safe handling, routing, and grounded responses.

## Run an evaluation

For RAG scores, first import the sample knowledge documents into the running API:

```sh
curl -fsS -X POST http://localhost:8080/api/knowledge/upload \
  -F 'file=@data/knowledge/demo_knowledge.json'
```

From the repository root, submit the test split:

```sh
curl -fsS -X POST http://localhost:8080/api/eval/run \
  -H 'Content-Type: application/json' \
  --data-binary @data/evaluation/support_test.json
```

The endpoint returns a job ID. Poll `/api/eval/jobs/{job_id}` until the job completes. Production deployments require an administrator bearer token on both requests. Dialogue evaluation calls the configured model for both responses and judging, so it may incur provider usage. Use validation results while tuning; keep the test split untouched until the configuration is fixed.

The RAG labels refer to the demonstration knowledge corpus. They measure retrieval against those sample documents and do not establish quality for another business's policies or real customer questions. The intent split is balanced for diagnostic comparisons; report per-intent scores and Macro-F1 alongside aggregate accuracy.
