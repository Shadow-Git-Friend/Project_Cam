# Kazakhstan Youth Academy Pilot Data Governance

This is an operational scaffold for a youth-football pilot in Kazakhstan. It is
not legal advice; review it with local counsel before recording minors.

## Legal Sources To Review

- Official Adilet text: Law of the Republic of Kazakhstan "On Personal Data and their Protection": <https://adilet.zan.kz/eng/docs/Z1300000094>
- Current jurisdiction overview: DLA Piper Data Protection Laws of the World, Kazakhstan: <https://www.dlapiperdataprotection.com/?c=KZ&t=law>

Operational defaults below are based on the current reading that personal data
collection and processing generally requires consent from the subject or legal
representative, and that consent must be confirmable. For minors, collect parent
or guardian consent and athlete assent before recording.

## Pilot Defaults

- Store raw video and raw frames locally by default; do not upload to cloud unless the consent form explicitly allows it.
- Use pseudonymous athlete IDs in filenames, JSON reports, C3D exports, and coach dashboards.
- Keep raw video/frame dumps out of Git. Only commit small synthetic fixtures or anonymized aggregate metrics.
- Do not use the system for medical diagnosis, injury prediction, talent ranking, selection, or rejection of children.
- Generate coach-facing reports only. Parent-facing exports require a separate review of wording and consent.
- The launcher/BLM is excluded from youth assessment pilots unless a separate safety protocol is approved.

## Consent Packet Requirements

Each consent record should include:

- Operator identity and contact.
- Athlete name, parent/guardian name, and consent date.
- Data collected: video, 2D/3D joint coordinates, derived metrics, reports, and optional C3D exports.
- Purpose: movement screening, coaching feedback, system validation, and aggregate product improvement.
- Retention period for raw media and derived reports.
- Whether data can be transferred to club staff, medical/physio partners, or external researchers.
- Whether any cross-border storage or processing is used.
- Withdrawal process and response SLA.
- Statement that the report is a coaching screen only, not diagnosis or talent ranking.

## Withdrawal And Deletion Workflow

Default workflow for a withdrawal request:

1. Log the request date, requester identity, athlete ID, and requested scope.
2. Stop new processing for the athlete while the request is reviewed.
3. Locate raw video, frame dumps, JSONL streams, reports, C3D/TRC/MOT exports, and backups by athlete ID.
4. Delete or anonymize records that are not legally required to be retained.
5. Send a written completion notice or reasoned refusal.

Use a 15-business-day internal deadline for withdrawal handling unless counsel
sets a stricter operational rule.

## Access Control

- Raw media: operator and technical maintainer only.
- Coach report: assigned club coach and operator.
- Aggregate metrics: founder/maintainer and approved pilot stakeholders.
- Exports to clinics or sports scientists: consent-specific and logged per transfer.

## Pilot Checklist

- Consent and assent forms ready in Russian, Kazakh, and English.
- Operator can run an assessment without exposing raw media in screen shares.
- Deletion test completed on a dummy athlete ID.
- Report wording reviewed for no diagnosis, no selection, and no injury-prediction claims.
- Club data recipient list approved before recording day.

