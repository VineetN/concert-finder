# Tailscale setup

Tailscale is used to give Node A and Node B a stable private IP so
Litestream can reference Node A's R2 bucket from Node B without exposing
credentials to the public internet.

## Steps

1. Install Tailscale on both machines: https://tailscale.com/download
2. `tailscale up` on each machine and sign in with the same account.
3. Note each machine's Tailscale IP (`tailscale ip -4`).
4. Add both IPs to your `.env` if needed for direct SSH-based rsync fallback.

## Fallback: rsync over SSH

If Litestream is overkill, a simple cron/APScheduler job on Node A can rsync
the DB file to Node B every hour:

```bash
rsync -avz data/concert.db user@<node-b-tailscale-ip>:/path/to/concert-finder/data/
```

On Windows, use `scp` from Git Bash or install rsync via Scoop:
```
scoop install rsync
```
