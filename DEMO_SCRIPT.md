# Affiliate Junction Demo Flow

Below is an example flow for delivering the Affiliate Junction demo to a mixed audience.
Note that it will take up to 5 minutes after deploying before data is fully flowing through the pipeline.

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
Highlight HCD and Iceberg/minio have been deployed and both are associated with the Presto Engine.  Note that Spark is another available engine, but for the purposes of this demo we're running it on-demand directly within Python

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/de214a08-fcf8-43f0-af0a-139acf0b833a">


### Data Manager

Expand HCD and Iceberg tabs, showing tables within the affiliate_junction catalog

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/6d1d8a2c-0825-4837-9e5a-b30c78f97f5e">


### Query Workspace

Notebook interface with persistent notebooks, and access to data sources in the side pane to quickly build federated queries.  Execute [one of the example queries](https://github.ibm.com/Data-Labs/affiliate-junction-demo?tab=readme-ov-file#single-datasource-operations) from the README.md file.  Note that queries can span multiple data sources

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/74391fa5-94ee-426f-8ba0-4e840b2c20d6">


## Affiliate Junction Web UI

Navigate to the Affiliate Junction landing page.  Reiterate there are multiple personas served by the demo dashboard.

<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/6d946973-27a4-45d0-93b0-9543c428e812">


### Query slider

The actual queries used to generate the displayed content are always available from each page.

Expand the query slider
<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/a660fce4-33ba-4fa1-8678-6d4c99d4e76c">

Expand one of the queries
<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/67db4aca-0bd4-42fd-a846-edad73a9aada">


### Publisher

Select one of the publishers from the drop down list in the sidebar.
<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/51c00bcc-bd35-43c5-8856-1ebf03b6e6bd">

Note that the page loads quickly.  The content is a mix of static metadata and timeseries data.  Both of these are served from an HCD query
(explore the query slider if curious).  This data is pre-computed by Spark and hits Presto historical data.  Since the queries are served from
HCD they are performant and support web-scale workloads.
<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/3b819066-3837-4fa6-83a2-d22f80eef718">


### Advertiser

Select one of the advertisers from the drop down list in the sidebar.
<img width="1414" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/6fce8de2-b09a-4097-a5d4-d2379ff8f8a3">

Make the same notes about timeseries data that is pre-computed and displayed quickly.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/9bd9aec1-3e40-4fb2-9142-25fbb4d1f6e3">

Scroll down to reveal the "Recent Conversions" element.  This list is a surface-level Presto query showing the conversions associated with this
advertiser.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/d462c1f6-766e-4ba6-885e-ea6cc2d66135">

Expand one of the cookie tabs.  Note the loading progress bar.  This is a more expensive analytical query suitable for reports or other
async workloads.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/da84941f-663b-45e6-8eae-e44c2a0566d0">

Once fully loaded the entire timeline of interactions between this cookie and different publishers is displayed.  You should click on one of the
cookies with "FRAUD" in the name since it will have a longer timeline.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/90545cf6-0aff-4a94-b83f-6fe880f80497">


### Admin

The Admin persona may be interested in fraudulent conversions.  

Click the "Fraud Reporting" link from the sidebar.

Note that this page loads across two different stages.  The first stage hits only the recent data stored within HCD and it returns quickly.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/144f99e5-9c8e-42ce-89ff-9789b1ff5eb0">

The second stage of this query issues a more expensive federated query from Presto that hits both the HCD and Iceberg data sources.  The results
of this query are used to refine the table and give a full 360-degree view for the admin.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/aba49d83-4560-4825-b2aa-d487b18c7eff">



### Services

Click on the "Demo Health" link at the bottom of the sidebar.

There are tabs associated with five services.  These are the services that power this demo.
* Generate Traffic - synthetic data generation
* HCD to Presto - ETL
* Presto Insights - Analytical queries
* Presto to HCD - Write pre-computed data for inexpensive consumption via Web UI

<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/07af3757-ff74-4c2c-8d8a-69cd8fdd45c9">

Click on the "Presto_to_hcd" tab.  Discuss that this gives visibility into everything that's happening in the backend, including capturing
all the queries that are issued.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/f8e9f0ee-c9ee-415d-92a9-3bf5ffa9f141">

Expand the query slider.  Note that there are both HCD and Presto queries.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/3863ecb0-3c72-4975-b02d-c31df49df72a">

Expand one of the Presto queries and explore its contents.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/ba431ad9-56e7-423b-b418-68245ee51d2d">


## Side Quests

### Spark

The Spark workloads aren't directly visible from this WUI.  

Consider [exploring the git repo for this project](https://github.ibm.com/Data-Labs/affiliate-junction-demo/blob/main/hcd_to_presto.py) and diving into the `hcd_to_presto.py` file.  Here you will see use of Pyspark to support ETL roll-up of impressions.
Here is a snippet of that code:

```python
            for bucket in range(int(os.getenv("AFFILIATE_JUNCTION_SALES_BUCKETS_COUNT"))):
                query = f"""
                SELECT bucket_date, publishers_id, advertisers_id, cookie_id
                FROM impressions_by_minute
                WHERE bucket_date = '{previous_minute}' AND bucket = {bucket}
                """
                
                rows = self.cassandra_connection.execute_query(
                    query=query,
                    query_description=f"Fetch impressions from bucket {bucket} for {previous_minute}"
                )
                for row in rows:
                    all_impressions.append({
                        'bucket_date': row.bucket_date,
                        'publishers_id': row.publishers_id,
                        'advertisers_id': row.advertisers_id,
                        'cookie_id': row.cookie_id,
                    })
            
            # Only proceed with Spark operations if we have data
            try:
                impressions_df = self.spark.createDataFrame(all_impressions)
                
                # Aggregate by publishers_id, advertisers_id, cookie_id to count impressions
                # Multiple records for the same combo within the time period should be counted
                # Include bucket_date in groupBy since all records should have the same bucket_date
                final_df = impressions_df.groupBy("publishers_id", "advertisers_id", "cookie_id", "bucket_date") \
                    .agg(count(lit(1)).alias("impressions")) \
                    .withColumnRenamed("bucket_date", "timestamp")
                
                impressions_aggregated = final_df.count()
```


### Presto WUI

You may want to show the Presto WUI in addition to the wx.d interface.  It shows real-time visibility into how the engine is being used with
charts and a live query viewer.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/7cba7af9-236d-4688-bb7e-00878ee0e9ee">

If you will be demonstrating ad-hoc queries, then using the SQL Client interface may be preferable to the wx.d notebook interface for some
scenarios.  There is less chrome and distraction around the text field allowing for easier focus on the query itself.
<img width="1430" alt="image" src="https://github.ibm.com/Data-Labs/affiliate-junction-demo/assets/521800/c302fc64-ce62-4028-813b-ccc1d2138e20">

