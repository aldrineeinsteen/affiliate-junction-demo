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

#### Traffic Generator Service
Generates synthetic affiliate marketing data and writes it to the HCD (Cassandra) database.

```
# Service operations
sudo systemctl start generate_traffic
sudo systemctl status generate_traffic
sudo systemctl restart generate_traffic

# View logs
journalctl -u generate_traffic -f
```

#### HCD to Presto Transfer Service
Transfers data from the HCD (Cassandra) database to Presto/Iceberg for analytical processing.

```
# Service operations
sudo systemctl start hcd_to_presto
sudo systemctl status hcd_to_presto
sudo systemctl restart hcd_to_presto

# View logs
journalctl -u hcd_to_presto -f
```

#### Presto Cleanup Service
Performs maintenance and cleanup operations on the Presto data lake storage.

```
# Service operations
sudo systemctl start presto_cleanup
sudo systemctl status presto_cleanup
sudo systemctl restart presto_cleanup

# View logs
journalctl -u presto_cleanup -f
```



### HCD CQL Console Access

Access `cqlsh` via `ssh` as the `watsonx` user with the command:

```
./hcd-1.2.3/bin/hcd cqlsh 172.17.0.1 -u cassandra -p cassandra
```



