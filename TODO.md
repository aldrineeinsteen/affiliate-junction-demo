
* Capture data on how many records are being generated and processed.
  Map to sparklines in admin section - one box for each service.


* Button to change the traffic generation parameters.  
  Update CQL to control thing
  Update traffic generator to monitor this on each loop and adjust as needed
  Show button to continue using defaults


* Add publishers dashboard



* CQL table for each service
 - service name
 - service description
 - last update timestamp
 - stats (json dict) - lifetime stats, lifetime runtime, average per time period
 - settings (json dict)

* stats:
 - timeseries all of the metrics - we will graph these.  retain 90 datapoints.  store as (unixtime,value) tuples




