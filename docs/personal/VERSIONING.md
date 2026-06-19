# Genius Pilot Versioning

Genius Pilot keeps the SunnyPilot upstream version as its base version and adds
a personal-build suffix.

Current alpha version:

```text
Genius Pilot 2026.002.000-gp.20260620.22
```

Format:

```text
<SunnyPilot base>-gp.<YYYYMMDD>.<patch>
```

Rules:

- `SunnyPilot base` follows the upstream SunnyPilot version in
  `sunnypilot/common/version.h`.
- `YYYYMMDD` is the date the Genius Pilot alpha patch is published.
- `patch` starts at `1` for the first Genius Pilot patch on that date and
  increments for each pushed alpha hotfix on the same date.
- When the SunnyPilot base is updated, keep the Genius suffix and reset the
  date/patch for the first Genius Pilot patch built from that base.
- Do not promote an alpha version to stable/latest until parked C3 evidence,
  no-cloud process evidence, and the required road-test phase are recorded.

Examples:

```text
2026.002.000-gp.20260620.1
2026.002.000-gp.20260620.2
2026.002.000-gp.20260620.3
2026.002.000-gp.20260620.4
2026.002.000-gp.20260620.5
2026.002.000-gp.20260620.6
2026.002.000-gp.20260620.7
2026.002.000-gp.20260620.8
2026.002.000-gp.20260620.9
2026.002.000-gp.20260620.10
2026.002.000-gp.20260620.11
2026.002.000-gp.20260620.12
2026.002.000-gp.20260620.13
2026.002.000-gp.20260620.14
2026.002.000-gp.20260620.15
2026.002.000-gp.20260620.16
2026.002.000-gp.20260620.17
2026.002.000-gp.20260620.18
2026.002.000-gp.20260620.19
2026.002.000-gp.20260620.20
2026.002.000-gp.20260620.21
2026.002.000-gp.20260620.22
2026.003.000-gp.20260705.1
```
