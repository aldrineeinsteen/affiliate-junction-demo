# affiliate-junction-demo
HCD + Preso demo of an affiliate marketing organization.  This project generates synthetic data that is spread across HCD and Presto/Iceberg instances within the watsonx.data instance.

This project also includes a WUI with views application to a number of distinct personas:

* Publisher view
* Advertiser view
* Administrator view





## WUI

This project includes a custom web UI that showcases how a customer can leverage the data endpoints to insights based on both realtime data stored within the Hyperconverged Database (Cassandra) and the Data Lake (Presto / Iceberg).




##  wx.d Interface

You may access the watsonx.data to issue ad-hoc queries.  


### Single Datasource Operations

View data from our RT tables hosted in HCD

```
-- Show avertiser impressions on each publisher's site bucketed by timestamp
SELECT * FROM  hcd.affiliate_junction.conversion_tracking LIMIT 10;

-- Show advertiser conversions
SELECT * FROM  hcd.affiliate_junction.conversion_tracking LIMIT 10;

```

View historical data view Presto.  This SQL interface supports more powerful data manipulation

```
# TODO
```


### Cross-Datasource Operations

The real power of watsonx.data is executing federated queries across diverse datasources.

```
# TODO
```


## Install

### Compatibility 

This repo is designed to run seamlessly on a watsonx.data Developer Edition single host.  It assumes Hyperconverged Database (HCD) has been installed.

This has been built and tested on Red Hat Enterprise Linux release 9.6.

The suite will run as expected when installed on top of this ITZ collection:
https://techzone.ibm.com/collection/ibm-watsonxdata-developer-base-image--hcd-cassandra


### Installation

Once Presto and HCD are available, execute `setup.sh` to install other pre-reqs and configure services.



## Troubleshooting


### Services

Backend ops are python scripts managed by `systemd` with unit files.

```
# Service ops for traffic generater
sudo systemctl start generate_traffic
sudo systemctl status generate_traffic
sudo systemctl restart generate_traffic

# View log files for generate_traffic
journalctl -u generate_traffic -f

```



### HCD CQL Console Access

Access `cqlsh` via `ssh` as the `watsonx` user with the command:

```
./hcd-1.2.3/bin/hcd cqlsh 172.17.0.1 -u cassandra -p cassandra
```



