# launchd Services for Seldon

## Observability Dashboard

File: `com.brock.seldon-observability-dashboard.plist`

Serves `scripts/observability_dashboard.py` on port 8765. Auto-starts at login,
restarts on crash (with 30-second throttle), logs to `~/.seldon-observability/`.

### Install

```bash
bash scripts/launchd/install_dashboard_service.sh
```

### Uninstall

```bash
bash scripts/launchd/uninstall_dashboard_service.sh
```

### Check status

```bash
launchctl list | grep seldon-observability
tail -f ~/.seldon-observability/dashboard.stderr.log
```

### Troubleshooting

- **Port conflict:** edit plist, change `--port 8765` to an unused port,
  unload + reload.
- **Python path wrong:** edit plist's ProgramArguments, re-run install.
- **Service keeps respawning:** check stderr log. Likely the dashboard is
  crashing on startup — usually `metrics.db` doesn't exist yet. Run the
  collector once first.
