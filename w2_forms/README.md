# W-2 Files

Keep W-2 JSON files in this folder.
You can also keep raw W-2 PDFs here.

Suggested naming:

- `w2_2025.json`
- `w2_template_2025.json`
- `W2_2025_<name>.pdf`

You can generate a template with:

```bash
python3 scripts/validate_w2_with_paystubs.py \
  --write-w2-template w2_forms/w2_template_2025.json \
  --paystubs-dir pay_statements \
  --year 2025
```

Extract from PDF to JSON:

```bash
python3 scripts/extract_w2_from_pdf.py \
  --w2-pdf w2_forms/W2_2025_Sasie_Redacted.pdf \
  --out w2_forms/w2_2025.json \
  --year 2025 \
  --render-scale 3.0
```
