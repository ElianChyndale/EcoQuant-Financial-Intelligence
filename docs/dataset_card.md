# Dataset Card

## Dataset Description

The EcoQuant temporal benchmark consists of 12 annual green-bond reports from
four issuers, spanning 2022--2024, with 64 frozen evaluation questions.

## Sources

| Issuer | Reports | Period |
|--------|---------|--------|
| AIB | Annual Financial Report | 2022, 2023, 2024 |
| ESB | Annual Report and Financial Statements | 2022, 2023, 2024 |
| Enel | Integrated Annual Report | 2022, 2023, 2024 |
| KfW | Financial Report | 2022, 2023, 2024 |

## Question Types

| Type | Count | Description |
|------|-------|-------------|
| evidence_lookup | 16 | Single-report fact retrieval |
| numeric_change | 16 | Cross-year numerical changes |
| contradiction_or_supersession | 16 | Temporal consistency |
| table_citation | 16 | Table and citation localization |

## Labels

- **Qualitative labels:** 16 hand-labeled questions
- **Audit labels:** 16 stratified subset of automatically derived labels
- **No inter-annotator agreement claimed**

## Data Rights

- Raw PDFs are not committed to the repository
- Source manifest records official URLs, SHA-256 hashes, and redistribution status
- Reports are fetched from official issuer archives
- Local cache is untracked (.gitignore)

## Limitations

- Small corpus (12 reports, 4 issuers)
- Small label set (16 + 16 questions)
- No inter-annotator agreement
- Synthetic corpus records used for deterministic testing
- Real corpus requires PDF Manager integration
