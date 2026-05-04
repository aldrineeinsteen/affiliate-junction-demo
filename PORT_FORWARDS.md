!# Port Forwarding for watsonx.data Services

This document explains the persistent port forwarding solution for the Affiliate Junction demo.

## Overview

The demo requires access to multiple watsonx.data services running in Kubernetes. Since these services are not directly accessible from outside the cluster, we use `kubectl port-forward` to expose them on the host machine.

## Problem

By default, `kubectl port-forward` is:
- **Session-based**: Terminates when SSH session ends
- **Not persistent**: Doesn't survive reboots
- **Manual**: Requires manual restart after failures

This causes issues when:
- SSH sessions disconnect
- System reboots
- Network interruptions occur
- Long idle periods

## Solution

We've created **systemd services** that manage port forwarding automatically. These services:
- ✅ Survive system reboots
- ✅ Auto-restart on failure (10-second delay)
- ✅ Log to journalctl for debugging
- ✅ Integrate with system service management

## Port Mappings

| Service | Local Port | K8s Service | K8s Port | Purpose |
|---------|-----------|-------------|----------|---------|
| Presto | 8443 | `ibm-lh-presto-svc` | 8443 | Query engine for ETL and analytics |
| watsonx.data UI | 9443 | `lhconsole-ui-svc` | 443 | Web console for watsonx.data |
| Minio API | 9000 | `ibm-lh-minio-svc` | 9000 | S3-compatible object storage API |
| Minio Console | 9001 | `ibm-lh-minio-svc` | 9001 | Minio web console |
| Hive Metastore | 9083 | `ibm-lh-mds-thrift-svc` | 8381 | Iceberg catalog metadata |

## Installation

### Quick Setup

```bash
# Make the setup script executable
chmod +x setup-port-forwards.sh

# Run the setup script (as root)
sudo ./setup-port-forwards.sh
```

The script will:
1. Verify prerequisites (kubectl, wxd namespace)
2. Install systemd service files
3. Stop any existing manual port forwards
4. Enable and start all services
5. Test connectivity to each service

### Manual Setup

If you prefer to set up manually:

```bash
# Copy service files
sudo cp *.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Stop existing manual port forwards
sudo pkill -f "kubectl port-forward"

# Start services
sudo systemctl start presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward
```

## Management

### Check Status

```bash
# Check all services
systemctl status presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Check individual service
systemctl status presto-port-forward
```

### View Logs

```bash
# Follow logs for a service
journalctl -u presto-port-forward -f

# View recent logs
journalctl -u presto-port-forward -n 50

# View logs for all port forward services
journalctl -u presto-port-forward -u wxd-ui-port-forward \
  -u minio-api-port-forward -u minio-console-port-forward \
  -u metastore-port-forward -f
```

### Restart Services

```bash
# Restart all services
systemctl restart presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Restart individual service
systemctl restart presto-port-forward
```

### Stop Services

```bash
# Stop all services
systemctl stop presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Stop individual service
systemctl stop presto-port-forward
```

### Disable Services

```bash
# Disable all services (won't start on boot)
systemctl disable presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward
```

## Testing Connectivity

### Test All Services

```bash
# Presto
curl -k https://localhost:8443/v1/info

# watsonx.data UI
curl -k https://localhost:9443

# Minio API
curl http://localhost:9000/minio/health/live

# Minio Console
curl http://localhost:9001

# Metastore (just check if port is open)
nc -zv localhost 9083
```

### Expected Responses

**Presto** should return JSON:
```json
{"nodeVersion":{"version":"0.286"},"environment":"production","coordinator":true,"starting":false}
```

**watsonx.data UI** should return HTML (status 200)

**Minio API** should return XML health status

**Minio Console** should return HTML (status 200)

**Metastore** should show "Connection succeeded"

## Troubleshooting

### Service Won't Start

1. Check if kubectl is configured:
   ```bash
   kubectl get pods -n wxd
   ```

2. Check service logs:
   ```bash
   journalctl -u presto-port-forward -n 50
   ```

3. Verify service exists in Kubernetes:
   ```bash
   kubectl get svc -n wxd | grep presto
   ```

### Port Already in Use

If a port is already in use:

```bash
# Find what's using the port
netstat -tulpn | grep 8443

# Kill the process
kill <PID>

# Restart the service
systemctl restart presto-port-forward
```

### Service Keeps Restarting

Check logs for errors:
```bash
journalctl -u presto-port-forward -f
```

Common issues:
- **Kubernetes pod not ready**: Wait for pods to be in Running state
- **Network issues**: Check cluster connectivity
- **Permission issues**: Ensure running as root

### After System Reboot

Services should start automatically. If not:

```bash
# Check if services are enabled
systemctl is-enabled presto-port-forward

# If not enabled, enable them
systemctl enable presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Start services
systemctl start presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward
```

## Integration with Demo Services

The following demo services depend on these port forwards:

- **`hcd_to_presto.service`**: Requires Presto (8443) and Metastore (9083)
- **`presto_to_hcd.service`**: Requires Presto (8443)
- **`presto_insights.service`**: Requires Presto (8443)
- **`presto_cleanup.service`**: Requires Presto (8443)
- **`uvicorn.service`**: Requires Presto (8443) for web UI queries

If port forwards fail, these services will log connection errors.

## Uninstallation

To remove the port forward services:

```bash
# Stop and disable services
systemctl stop presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

systemctl disable presto-port-forward wxd-ui-port-forward \
  minio-api-port-forward minio-console-port-forward metastore-port-forward

# Remove service files
rm /etc/systemd/system/presto-port-forward.service
rm /etc/systemd/system/wxd-ui-port-forward.service
rm /etc/systemd/system/minio-api-port-forward.service
rm /etc/systemd/system/minio-console-port-forward.service
rm /etc/systemd/system/metastore-port-forward.service

# Reload systemd
systemctl daemon-reload
```

## Architecture Notes

### Why Port Forwarding?

watsonx.data Developer Edition runs in Kubernetes (Kind cluster) with services exposed as ClusterIP. These are only accessible from within the cluster. Port forwarding creates a tunnel from the host to the cluster.

### Alternative Approaches

Other options considered:
- **NodePort**: Requires modifying Helm charts, not portable
- **LoadBalancer**: Not available in Kind clusters
- **Ingress**: Adds complexity, requires additional setup
- **Host networking**: Security concerns, port conflicts

Port forwarding via systemd services provides the best balance of:
- Simplicity
- Reliability
- Maintainability
- Security

### Performance Impact

Port forwarding has minimal performance impact:
- Low CPU usage (~0.1% per service)
- Low memory usage (~50MB per service)
- No data transformation overhead
- Direct TCP tunneling

## See Also

- [`DEPLOYMENT.md`](DEPLOYMENT.md) - Full deployment guide
- [`SERVICES.md`](SERVICES.md) - Demo service documentation
- [`README.md`](README.md) - Project overview