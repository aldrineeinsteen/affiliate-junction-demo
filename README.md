# affiliate-junction-demo
HCD + Preso demo of an affiliate marketing organization.  This project generates synthetic data that is spread across HCD and Presto/Iceberg instances within the watsonx.data instance.

**Purpose:** This demonstration showcases watsonx.data's federated architecture capabilities through:
- **RT web-scale queries** using HCD (Cassandra) for real-time operational data
- **Historical/Analytic queries** using Presto backed by Iceberg tables for complex analytics
- **Federated queries** across different data sources combining operational and analytical workloads
- **Full transparency** into the queries that are used to deliver a complete WUI + ETL solution

This project also includes a WUI with views application to a number of distinct personas:

* Publisher view
* Advertiser view
* Administrator view

## Table of Contents

- [WUI](#wui)
- [wx.d Interface](#wxd-interface)
- [Other Interfaces](#other-interfaces)
- [Install](#install)
- [Troubleshooting](#troubleshooting)

### Additional Documentation
- [Demo Script](DEMO_SCRIPT.md)
- [Techzone Collection](https://techzone.ibm.com/collection/watsonxdata-data-labs-demos/journey-affiliate-junction)
- [Data Labs WUI Framework](https://github.ibm.com/Data-Labs/datalabs-wui-framework)




## WUI

This project includes a custom web UI that showcases how a customer can leverage the data endpoints to insights based on both realtime data stored within the Hyperconverged Database (Cassandra) and the Data Lake (Presto / Iceberg).

The web interface provides role-based dashboards demonstrating federated analytics across watsonx.data's hybrid storage architecture. Access the interface at `http://localhost:10000` after running the setup.




### Available Screens

#### Login

Login with the user `watsonx` and password `watsonx.data`.

<img width="1483" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/543d989d-3dcf-4dd9-be66-6a2484858f86">


#### Dashboard Overview (Index)
**Route:** `/`

The main landing page provides a comprehensive overview of the affiliate marketing ecosystem with real-time metrics and navigation to specialized views. Features quick access to key performance indicators and system health status.  It serves to orient attendees to the purpose and flow of the data as part of this demo.

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/6c0c58d6-6e40-4ab4-a707-e16908f2251c">


#### Query Viewer

Available on every screen throughout the application, the Query Viewer provides real-time transparency into the federated data access patterns that power the affiliate marketing analytics. This feature demonstrates watsonx.data's ability to seamlessly coordinate queries across multiple data sources.

**Key Features:**
- **Real-time Query Monitoring**: Live tracking of all SQL operations as they execute against HCD (Cassandra) and Presto/Iceberg
- **Federated Query Visualization**: Clear distinction between operational queries (HCD) and analytical queries (Presto) with separate counters
- **Query Details Panel**: Expandable view showing complete SQL syntax, execution parameters, and performance metrics
- **Execution Timing**: Millisecond-precision timing for performance analysis and optimization
- **Query History**: Persistent log of recent database operations with status indicators (pending, success, error)

**Technical Demonstration:**
The Query Viewer showcases the dual-write architecture in action by displaying how the same business logic triggers different query patterns:
- **HCD Queries**: Fast, partition-targeted reads for real-time dashboard updates
- **Presto Queries**: Complex analytical joins across time-partitioned data for trend analysis
- **Cross-source Correlation**: Visual representation of how federated queries combine operational and analytical data

**Access Method:**
Click the query panel toggle button (typically located on the right side of any screen) to reveal the sliding panel interface. The badge indicator shows the count of unread queries, and the panel maintains separate counters for HCD and Presto operations.

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/a663601b-906b-4987-8c38-123dc43d7ff5">

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/2b2a3db4-13ab-4d7b-8889-0cd966edaa77">


#### Publisher Dashboard
**Route:** `/publisher/{publisher_id}`

Dedicated view for content publishers showing their performance metrics including:
- Real-time impression tracking from HCD
- Historical conversion analytics from Presto/Iceberg  
- Revenue trends and publisher-specific KPIs
- Cross-advertiser performance comparisons

Demonstrates web-scale access to pre-processed data that has been staged inside HCD

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/ebceb4b5-db9d-401a-aa66-c8cd561f944e">


#### Advertiser Dashboard  
**Route:** `/advertiser/{advertiser_id}`

Campaign management interface for advertisers featuring:
- Live campaign performance monitoring
- Conversion tracking and attribution analysis
- ROI calculations across publisher networks
- Historical trend analysis for optimization

Showcases dual-write pattern benefits by combining immediate feedback from HCD with deep analytical views from the data lake.

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/73681f5f-8d5f-47b7-bb02-c137a4da8b9d">

Dive into the historical journey of any specific conversion.  We by showing the list of recent coversions (via HCD):

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/728b84dc-4d1a-41bf-89b6-c750039679ec">

Expanding any of the accordion elements generates a Presto query that shows the entire timeline from first impression to conversion:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/47312bec-270e-4c34-a1bb-9121e0d85e80">


#### Fraud Detection Dashboard
**Route:** `/fraud`

Advanced analytics dashboard for identifying suspicious affiliate activity:
- Anomaly detection using historical patterns
- Real-time fraud scoring algorithms  
- Cross-correlation analysis between publishers and advertisers
- Investigation tools for manual review

Demonstrates complex analytical capabilities enabled by watsonx.data's federated query engine across multiple data sources.

This page loads in two stages.  The table is first generated with data from a fast Presto query against the HCD datasource:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/837f79de-7ed7-45bf-9549-e1f66fa13087">

The page is then refined by looking at all historical information using a federated HCD/Iceberg query via Presto:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/457a86c0-a47a-40b4-b8eb-045b69a92efa">



#### Services Administration
**Route:** `/services`

System administration interface for monitoring the data pipeline:
- Real-time service health monitoring
- Data flow metrics between HCD and Presto
- System performance dashboards
- Service restart and configuration management

Provides visibility into the backend ETL processes and dual-write architecture maintenance.  There are five such services.  The charts show useful information detailing the data volume and associated timing:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/e63bf795-3bd0-4870-9afd-220db0cb73a3">

All queries associated with the services themselves are also captured.  These queries are visible from within the query discovery slider:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/be775619-ed1c-4655-96e5-ea46d3c8bdc7">

Some services have tunables that can be dynamically changed from their defaults from within this screen.  Changes take affect within a minute:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/db6fe4df-eb20-4885-89d4-606915c39bf9">



##  wx.d Interface

You may access the watsonx.data to issue ad-hoc queries.  


### Single Datasource Operations

View data from our RT tables hosted in HCD

```sql
-- Show avertiser impressions on each publisher's site bucketed by timestamp
SELECT * FROM  hcd.affiliate_junction.conversion_tracking LIMIT 10;

-- Show advertiser conversions
SELECT * FROM  hcd.affiliate_junction.conversion_tracking LIMIT 10;

```

View historical data view Presto.  This SQL interface supports more powerful data manipulation

```sql
-- Show top performing publishers by total impressions over last 24 hours
SELECT 
  publishers_id,
  SUM(impressions) as total_impressions,
  COUNT(DISTINCT advertisers_id) as unique_advertisers
FROM iceberg_data.affiliate_junction.impression_tracking
WHERE timestamp >= current_timestamp - INTERVAL '1' DAY
GROUP BY publishers_id
ORDER BY total_impressions DESC
LIMIT 10;
```


### Cross-Datasource Operations

The real power of watsonx.data is executing federated queries across diverse datasources.

```sql
-- Join real-time impressions with historical conversion rates
SELECT 
  hcd_data.publishers_id,
  hcd_data.recent_impressions,
  iceberg_data.avg_conversion_rate,
  ROUND(hcd_data.recent_impressions * iceberg_data.avg_conversion_rate / 100, 2) as predicted_conversions
FROM (
  SELECT 
    publishers_id,
    COUNT(*) as recent_impressions
  FROM hcd.affiliate_junction.impressions_by_minute
  WHERE bucket_date >= DATE_ADD('minute', -5, now())
  GROUP BY publishers_id
) hcd_data
JOIN (
  SELECT 
    publishers_id,
    AVG(CAST(impressions AS DOUBLE)) as avg_impressions,
    COUNT(*) * 100.0 / AVG(CAST(impressions AS DOUBLE)) as avg_conversion_rate
  FROM iceberg_data.affiliate_junction.impression_tracking
  WHERE timestamp >= DATE_ADD('day', -7, now())
  GROUP BY publishers_id
  HAVING AVG(CAST(impressions AS DOUBLE)) > 0
) iceberg_data ON hcd_data.publishers_id = iceberg_data.publishers_id
ORDER BY predicted_conversions DESC;
```


## Other Interfaces

### Presto Console

The open source Presto console is another good window into the activity occuring within wx.d.  Since all ETL activities occurs every minute, you will typically see active queries and statistics showing usage:

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/0756c8e5-2215-4219-9b97-09143cb483dd">

The console also includes a SQL interface to enter your own queries.  This may be an easier web-based location to explore queries that the wx.d built-in notebook feature.

<img width="1522" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/f326419e-60a7-4faa-9c16-47e810f2849e">



## Install

### Compatibility 

This repo is designed to run seamlessly on a watsonx.data Developer Edition single host.  It assumes Hyperconverged Database (HCD) has been installed.

This has been built and tested on Red Hat Enterprise Linux release 9.6.

The suite will run as expected when installed on top of this ITZ collection:
https://techzone.ibm.com/collection/ibm-watsonxdata-developer-base-image--hcd-cassandra


### Installation

Once Presto and HCD are available, execute `setup.sh` to install other pre-reqs and configure services.


## Troubleshooting


### Starting Over

If services are not behaving as expected (e.g. data not flowing, slow performance) then restart the server.
On boot the server will truncate all tables (thus improving performance) and will restart all services
in the proper order.

Note -- issuing shutdown / reboot commands from within the ssh console often causes the server to land in
a "stuck" state.  Make sure the host actually reboots and powers off from within the ITZ console itself.


### Services

Backend ops are python scripts managed by `systemd` with unit files.

#### Traffic Generator Service
Generates synthetic affiliate marketing data and writes it to the HCD (Cassandra) database.

```bash
# Service operations
sudo systemctl start generate_traffic
sudo systemctl status generate_traffic
sudo systemctl restart generate_traffic

# View logs
journalctl -u generate_traffic -f
```

#### HCD to Presto Transfer Service
Transfers data from the HCD (Cassandra) database to Presto/Iceberg for analytical processing.

```bash
# Service operations
sudo systemctl start hcd_to_presto
sudo systemctl status hcd_to_presto
sudo systemctl restart hcd_to_presto

# View logs
journalctl -u hcd_to_presto -f
```

#### Presto Cleanup Service
Performs maintenance and cleanup operations on the Presto data lake storage.

```bash
# Service operations
sudo systemctl start presto_cleanup
sudo systemctl status presto_cleanup
sudo systemctl restart presto_cleanup

# View logs
journalctl -u presto_cleanup -f
```

#### Presto to HCD Transfer Service
Transfers data from Presto/Iceberg back to the HCD (Cassandra) database for specific use cases.

```bash
# Service operations
sudo systemctl start presto_to_hcd
sudo systemctl status presto_to_hcd
sudo systemctl restart presto_to_hcd

# View logs
journalctl -u presto_to_hcd -f
```

#### Presto Insights Service
Generates analytical insights and reports from Presto/Iceberg data.

```bash
# Service operations
sudo systemctl start presto_insights
sudo systemctl status presto_insights
sudo systemctl restart presto_insights

# View logs
journalctl -u presto_insights -f
```

#### Web UI Service (Uvicorn)
Serves the FastAPI web application providing the user interface for the affiliate marketing analytics platform.

```bash
# Service operations
sudo systemctl start uvicorn
sudo systemctl status uvicorn
sudo systemctl restart uvicorn

# View logs
journalctl -u uvicorn -f
```



### HCD CQL Console Access

Access `cqlsh` via `ssh` as the `watsonx` user with the command:

```bash
./hcd-1.2.3/bin/hcd cqlsh 172.17.0.1 -u cassandra -p cassandra
```



