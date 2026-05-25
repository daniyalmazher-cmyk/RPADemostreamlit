# KYC Rules — Automated Checks

Every application that comes through the bot is run against the five rules
below. The combined outcome is shown in the `status` column on the dashboard.

## Status meanings

| Status | What it means | When it happens |
|---|---|---|
| `auto_approve` | Safe to open the account without operator review. | Every rule passed. |
| `needs_review` | Operator must look at the application before deciding. | A **warning** rule failed (no **blocking** rule did). |
| `auto_reject` | Application is declined automatically. | At least one **blocking** rule failed. |

The `failed_rules` column lists every rule that did not pass, separated by
semicolons (e.g. `id_checksum;sanctions`).

## The five rules

### 1. `id_format` — blocking
Confirms the ID number is exactly 10 digits and starts with **1** (Saudi
citizen — National ID) or **2** (resident — Iqama). Anything else is treated
as an unreadable / invalid document and rejected.

### 2. `id_checksum` — blocking
Validates the last digit of the ID against the published Saudi National ID
checksum formula. A mismatch usually means the OCR misread one of the
digits, but it can also indicate a fabricated number. Either way the
application is rejected so a human can re-key the ID from the source image.

### 3. `age_18plus` — blocking
Computes the applicant's age from `dob_gregorian` and requires it to be at
least 18. If the date of birth could not be extracted from the document the
rule produces a warning (the application drops to `needs_review` rather than
being rejected outright) so the operator can read the card themselves.

### 4. `name_present` — warning
At least one of the Arabic name or the English name must have been
extracted. If both are missing the application is sent to `needs_review`;
it is never auto-rejected on names alone, because Arabic OCR can fail on
otherwise-valid cards.

### 5. `sanctions` — blocking
Screens the extracted Arabic and English names against the internal
sanctions list. Any match — even a partial one — auto-rejects the
application. False positives go to operations to clear manually.
