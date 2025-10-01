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
* Dashboards to servediverse personas:
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

* **Login**.  Note support for SSO and RBAC
* **Infrastructure Manager**.  Highlight HCD and Iceberg/minio have been deployed and both are associated with the Presto Engine.  Note that Spark is another available engine, but for the purposes of this demo we're running it on-demand directly within Pythoni
* **Data Manager**.  Expand HCD and Iceberg tabs, showing tables within the affiliate_junction catalog
* **SQL Query**.  Notebook interface with persistant notebooks, and access to data sources in the side pane to quicklly build federated queries.  Execute [one of the example queries](https://github.ibm.com/Data-Labs/affiliate-junction-demo?tab=readme-ov-file#single-datasource-operations) from the README.md file.  Note that queries can span multiple data sources



## Affiliate Junction Web UI



## Side Quests

### Presto WUI



