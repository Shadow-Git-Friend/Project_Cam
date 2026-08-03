# Competitor map — what academies pay for today

Prices are public-order-of-magnitude *(verify per-deal; vendors negotiate)*.
The column that wins deals: **what they lock behind a paywall that we ship
on-prem.**

| Vendor | Category | Typical cost | Paywall / lock-in | Where camera-only on-prem wins |
|---|---|---|---|---|
| Catapult | GPS/IMU vests | ~$100–500 per athlete/yr + hardware | per-athlete subscription, cloud analytics tiers, proprietary export | whole-squad coverage with zero per-child hardware; kids' sizes/compliance issues disappear; data stays on-prem |
| STATSports | GPS vests | similar per-athlete/yr | same model | same as above |
| Hudl (incl. Focus cameras) | video platform | $1–10k/yr per team tier | cloud storage tiers, analysis seats, no raw-data export on lower tiers | on-prem storage, unlimited local seats, raw CSV/Parquet always |
| Wyscout | scouting video/data | $5–20k/yr club tier | database subscription; youth/regional coverage thin — KZ academies barely covered | we generate the data locally instead of licensing someone else's |
| SkillCorner | broadcast-video tracking | enterprise | needs broadcast feed — academies have none | works from our own fixed cameras |
| SciSports | analytics SaaS | enterprise | cloud, models opaque | open-core models, uncertainty published |
| EasyCoach | academy management (existing **KFF partner**) | per-club SaaS | administrative layer (attendance, planning), no CV metrics | complementary, not competitive — integration target, not rival: export our KPIs into their player profiles *(partnership conversation via KFF)* |
| Veo | 2-camera auto-filming | ~$1–2k cam + ~$1–3k/yr | cloud processing subscription, highlights-oriented, no biomech/load | full metric stack, no recurring cloud fee, minors' video stays local |

## Positioning sentence

> Open-core, on-prem, camera-only, KZ-localized, no per-player subscription —
> the metrics of a vest + the video of an analyst, from hardware the academy
> owns.

## Defensive notes

- Veo is the perception-price anchor ("cameras that film themselves for
  €2k") — differentiate on *metrics and biomech*, never on filming.
- Catapult/STATSports will argue accelerometer-grade load accuracy; our
  answer is the validation ladder (METRICS.md): a published parallel-session
  MAE table, plus the KPIs vests cannot do at all (biomech angles, tactical
  maps, scanning) and squad-wide coverage without opt-in hardware.
- EasyCoach's KFF relationship is a channel, not a threat — their product
  stops where ours starts.
