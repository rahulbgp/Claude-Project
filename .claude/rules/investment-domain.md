# Investment & Lending Domain Rules

## Regulatory Framework
- All decisions must comply with **RBI Fair Lending Guidelines 2023**
- No discrimination based on age (beyond eligibility window), gender, religion, or caste
- Every decision must be logged with a trace ID for audit purposes

## Eligibility Thresholds
- Minimum credit score: **700** (CIBIL scale 300–900)
- Maximum EMI-to-Income ratio: **40%** of monthly income
- Eligible age range: **21–60 years**
- Employment stability: Salaried > Self-Employed > Contract; Unemployed = ineligible

## Loan Products
- Personal loans: up to 10x annual income
- Default tenure: 60 months; default interest rate: 10% p.a.
- EMI formula: P x r x (1+r)^n / ((1+r)^n - 1) where r = monthly rate, n = months

## Risk Bands
| Band | Criteria |
|------|----------|
| LOW | Composite score >= 0.75 |
| MEDIUM | Composite score 0.50-0.74 |
| HIGH | Composite score 0.25-0.49 -> manual review |
| CRITICAL | Composite score < 0.25 -> auto-reject |

## Bias Monitoring
- Flag young applicants (21-24) rejected without clear financial reason
- Flag near-retirement applicants (55-60) rejected — verify age is not the cause
- Flag Contract/Self-Employed rejections — confirm financial basis only
