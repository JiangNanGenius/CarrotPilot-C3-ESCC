# Genius Pilot Install Entry

This branch hosts the current install entrypoints for the same GitHub repository.

- `i`: C3 binary installer for the maintained `genius/c3` branch.
- `x`: C3 binary installer for the Genius Pilot alpha architecture branch.
- `s`: shell installer for SSH maintenance and channel switching.

Default install target:

```text
JiangNanGenius/CarrotPilot-C3-ESCC.git
genius/c3
```

Genius Pilot alpha C3 target:

```text
JiangNanGenius/CarrotPilot-C3-ESCC.git
alpha-sunnypilot-c3
```

Current published release: `8cfcdcfb5` (2026-09-14), including segmented
speed-limit offsets and the latest C3 cruise, traffic, HUD, and communication
fixes. The fixed `/i` entrypoint always installs the latest `genius/c3` commit.

The numbered test tags are kept only for history. Use these fixed entrypoints for normal installs.
