# affiliate-junction-demo
HCD + Preso demo of an affiliate marketing organization.  This project generates synthetic data that is spread across HCD and Presto/Iceberg instances within the watsonx.data instance.

This project also includes a WUI with views application to a number of distinct personas:

* Publisher view
* Advertiser view
* Administrator view






## Services

Backend ops are python scripts managed by `systemd` with unit files.

```
# Service ops for traffic generater
sudo systemctl start traffic_generator
sudo systemctl status traffic_generator
sudo systemctl restart traffic_generator

# View log files for traffic generator
journalctl -u traffic_generator -f

```



## HCD CQL Console Access

Access `cqlsh` via `ssh` as the `watsonx` user with the command:

```
./hcd-1.2.3/bin/hcd cqlsh 172.17.0.1 -u cassandra -p cassandra
```



