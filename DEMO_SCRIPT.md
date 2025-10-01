# Affiliate Junction Demo Flow

Below is an example flow for delivering the Affiliate Junction demo to a mixed audience.

## Introduction

### Use Case

Affiliate Junction is an affiliate marketing company.  Affiliate marketing is a performance-based business model where a company rewards individuals or 
other businesses (called affiliates) for driving traffic, leads, or sales to the company’s products or services.

Affiliates promote a company’s offerings through links, ads, or content. When a user clicks on an affiliate’s link and makes a purchase (or completes another 
desired action), the affiliate earns a commission.


### Requirements

Affiliate marketing requires:

* Very low latency web-scale writes to track publisher impressions
* High performance analytics engines to accurately attribute sales to a specific publisher
* Dashboards to serve diverse personas:
  * Publisher - View number of recorded impressions, conversion count, and total commission payout
  * Advertiser - View conversion details and cost
  * Admin - Identify suspected click-fraud behavior

### Components Demonstrated

This demo makes use of the watsonx.data suite, specifically:

* HCD (Cassandra) - Web-scale, low-latency, wide-column no-SQL database.  This provides high performance reads / writes to power impression tracking and dashboards
* Presto / Iceberg - Analytics engine with infinitely expandable object storage data
* Spark - Scale-out ETL engine to move data from HCD to Presto
* Presto federated queries - interrogate multiple data sources in the same query


## watsonx.data

This demo makes use of the wx.d Developer Edition.  This is an all-in-one install that runs in containers on a single host.  There are some limitations associated
with wx.d Developer Edition.  This edition is available for customers to test without any licensing requirements.

### Login
Note support for SSO and RBAC

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/21d87144-2365-490c-9d04-9205aab38da2">

### Infrastructure Manager
Highlight HCD and Iceberg/minio have been deployed and both are associated with the Presto Engine.  Note that Spark is another available engine, but for the purposes of this demo we're running it on-demand directly within Pythoni

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/de214a08-fcf8-43f0-af0a-139acf0b833a">


### Data Manager

Expand HCD and Iceberg tabs, showing tables within the affiliate_junction catalog

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/6d1d8a2c-0825-4837-9e5a-b30c78f97f5e">


### Query Workspace

Notebook interface with persistant notebooks, and access to data sources in the side pane to quicklly build federated queries.  Execute [one of the example queries](https://github.ibm.com/Data-Labs/affiliate-junction-demo?tab=readme-ov-file#single-datasource-operations) from the README.md file.  Note that queries can span multiple data sources

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/74391fa5-94ee-426f-8ba0-4e840b2c20d6">


## Affiliate Junction Web UI

Reiterate there are multiple personas served by thei demo dashboard.

### Query slider

The actual queries used to generate the displayed content are always available from each page.

* Expand the query slider
* Expand one of the queries
  

### Publisher

Select one of the publishers from 

### Advertiser


### Admin


### Services


## Side Quests

### Spark


### Presto WUI



