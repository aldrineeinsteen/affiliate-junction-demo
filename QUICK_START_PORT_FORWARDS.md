# Quick Start: Port Forwarding Setup

## TL;DR

After system reboot or when port forwards stop working:

```bash
cd /root/affiliate-junction-demo
sudo ./setup-port-forwards.sh
```

That's it! The script will set up persistent port forwarding for all watsonx.data services.

---

## What This Does

Creates 5 systemd services that automatically:
- Forward Presto (8443)
- Forward watsonx.data UI (9443)
- Forward Minio API (9000)
- Forward Minio Console (9001)
- Forward Hive Metastore (9083)

These services will:
- ✅ Start automatically on boot
- ✅ Restart automatically on failure
- ✅ Log to journalctl for debugging

---

## Quick Commands

### Check if port forwards are running
```bash
systemctl status presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward
```

### Restart all port forwards
```bash
systemctl restart presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward
```

### View logs
```bash
# All port forward logs
journalctl -u presto-port-forward -u wxd-ui-port-forward \
  -u minio-api-port-forward -u minio-console-port-forward \
  -u metastore-port-forward -f

# Just Presto
journalctl -u presto-port-forward -f
```

### Test connectivity
```bash
# Presto
curl -k https://localhost:8443/v1/info

# watsonx.data UI
curl -k https://localhost:9443

# Minio
curl http://localhost:9000/minio/health/live
```

---

## When to Use

Run the setup script when:
- ❌ Web UI shows "Max retries exceeded" errors
- ❌ watsonx.data console is not accessible
- ❌ After system reboot
- ❌ After long idle periods
- ❌ After SSH session disconnects

---

## Files Created

The setup script creates these files:

**In current directory:**
- `presto-port-forward.service`
- `wxd-ui-port-forward.service`
- `minio-api-port-forward.service`
- `minio-console-port-forward.service`
- `metastore-port-forward.service`
- `setup-port-forwards.sh` (this installer)

**In /etc/systemd/system/:**
- Copies of all .service files (installed by script)

---

## Full Documentation

For detailed information, see [`PORT_FORWARDS.md`](PORT_FORWARDS.md)