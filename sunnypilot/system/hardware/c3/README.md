# C3 specific hardware code

`c3` is known as `tici` and comma three by comma. Not to confuse it with `c3x` which is known as `tizi`.

## Bench Rescue SSH

`rescue_ssh.sh` is a local bench-recovery helper for clone C3 alpha testing. It
is bench-only opt-in, inert by default, and must not be treated as a normal
login or cloud registration path.

To arm it locally for one boot, set:

```bash
CARROT_C3_RESCUE_ENABLE=1
```

or create this local marker on the device:

```bash
/data/carrotpilot/bench_rescue_enable
```

Credentials are never hardcoded in the release tree. Provide a temporary bench
password with `CARROT_C3_RESCUE_PASSWORD`, or provide authorized keys with
`CARROT_C3_RESCUE_PUBKEY` or `/data/carrotpilot/bench_rescue_authorized_keys`.

The helper may set `SshEnabled=1` only after it is explicitly armed. It never
writes `GithubSshKeys`, never contacts GitHub, and never depends on comma,
Sunnylink, or any cloud registration service.
