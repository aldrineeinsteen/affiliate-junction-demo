# Architecture Documentation - Affiliate Junction Demo

Complete architectural overview of the Affiliate Junction demo, explaining how watsonx.data Developer Edition, HCD (IBM Cassandra), and the custom application work together.

## Table of Contents

1. [System Overview](#system-overview)
2. [Infrastructure Architecture](#infrastructure-architecture)
3. [watsonx.data Developer Edition](#watsonxdata-developer-edition)
4. [HCD (IBM Cassandra) Integration](#hcd-ibm-cassandra-integration)
5. [Data Flow Architecture](#data-flow-architecture)
6. [Application Components](#application-components)
7. [Network Architecture](#network-architecture)
8. [Storage Architecture](#storage-architecture)
9. [Service Architecture](#service-architecture)
10. [Query Federation](#query-federation)

---

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        IBM Cloud VM                              │
│                    (RHEL 9, 8 vCPU, 32GB RAM)                   │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              watsonx.data Developer Edition                 │ │
│  │                  (Kubernetes - Kind)                        │ │
│  │                                                             │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │ │
│  │  │  Presto  │  │  Minio   │  │   HMS    │  │ Console  │  │ │
│  │  │  (Query) │  │ (S3/Ice) │  │(Catalog) │  │   (UI)   │  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │ │
│  │       ↓              ↓              ↓                      │ │
│  │  Port Forwards (systemd services)                         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                          ↓                                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  Native Services                            │ │
│  │                                                             │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │ │
│  │  │   HCD    │  │ Traffic  │  │   ETL    │  │  Web UI  │  │ │
│  │  │(Cassand) │  │Generator │  │ Services │  │ (FastAPI)│  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Infrastructure** | IBM Cloud VPC | - | VM hosting |
| **OS** | RHEL 9 | 9.x | Base operating system |
| **Container Runtime** | Docker | 24.x | Container execution |
| **Kubernetes** | Kind | 0.20.x | Local K8s cluster |
| **watsonx.data** | Developer Edition | 2.0.x | Data lakehouse platform |
| **Query Engine** | Presto | 0.286 | Federated query engine |
| **Object Storage** | Minio | Latest | S3-compatible storage |
| **Catalog** | Hive Metastore | 3.x | Iceberg catalog |
| **Operational DB** | HCD (Cassandra) | 1.2.5 | Real-time data store |
| **Data Format** | Apache Iceberg | 1.x | Table format |
| **ETL** | PySpark | 3.5.x | Data transformation |
| **Web Framework** | FastAPI | 0.104.x | REST API & UI |
| **Web Server** | Uvicorn | 0.24.x | ASGI server |

---

## Infrastructure Architecture

### IBM Cloud VPC Setup

The demo runs on a single IBM Cloud VPC virtual machine with the following characteristics:

#### VM Specifications
- **Profile**: `bx2-8x32` (8 vCPUs, 32GB RAM)
- **OS**: Red Hat Enterprise Linux 9
- **Storage**: 100GB boot volume
- **Network**: Private subnet with floating IP

#### Network Components
```
Internet
    ↓
Floating IP (Public)
    ↓
Security Group (Firewall)
    ↓
VM Private IP
    ↓
VPC Subnet
```

#### Security Group Rules

| Port | Protocol | Purpose | Access |
|------|----------|---------|--------|
| 22 | TCP | SSH | Admin access |
| 8443 | TCP | Presto Console | Query interface |
| 9000 | TCP | Minio API | S3 operations |
| 9001 | TCP | Minio Console | Storage UI |
| 9083 | TCP | Hive Metastore | Catalog access |
| 9443 | TCP | watsonx.data UI | Management console |
| 10000 | TCP | Affiliate Junction UI | Demo application |

#### Automated Provisioning

The [`setup-vm.sh`](setup-vm.sh) script automates:
1. VPC and subnet creation
2. Security group configuration
3. SSH key generation and upload
4. VM provisioning with cloud-init
5. Floating IP assignment
6. Optional auto-installation via cloud-init

---

## watsonx.data Developer Edition

### What is watsonx.data Developer Edition?

watsonx.data Developer Edition is a **containerized, Kubernetes-based** deployment of IBM's data lakehouse platform. It runs entirely within a Kind (Kubernetes in Docker) cluster on a single VM.

### Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Kind Cluster (kind-wxd)                   │
│                                                               │
│  Namespace: wxd                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐  ││
│  │  │  Presto Coordinator (ibm-lh-presto)              │  ││
│  │  │  - Query execution engine                        │  ││
│  │  │  - Federation coordinator                        │  ││
│  │  │  - Connector management                          │  ││
│  │  │  Port: 8443 (HTTPS), 8481 (REST)               │  ││
│  │  └──────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐  ││
│  │  │  Minio (ibm-lh-minio)                           │  ││
│  │  │  - S3-compatible object storage                  │  ││
│  │  │  - Iceberg table data storage                    │  ││
│  │  │  - Parquet file storage                          │  ││
│  │  │  Ports: 9000 (API), 9001 (Console)             │  ││
│  │  └──────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐  ││
│  │  │  Hive Metastore (ibm-lh-mds-thrift)             │  ││
│  │  │  - Iceberg catalog                               │  ││
│  │  │  - Table metadata management                     │  ││
│  │  │  - Schema registry                               │  ││
│  │  │  Port: 8381 (Thrift)                            │  ││
│  │  └──────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐  ││
│  │  │  watsonx.data Console (lhconsole-ui)            │  ││
│  │  │  - Web-based management UI                       │  ││
│  │  │  - Query editor                                  │  ││
│  │  │  - Catalog browser                               │  ││
│  │  │  Port: 443 (HTTPS)                              │  ││
│  │  └──────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  │  ┌──────────────────────────────────────────────────┐  ││
│  │  │  PostgreSQL (wxd-pg-postgres)                    │  ││
│  │  │  - Metastore backend                             │  ││
│  │  │  - Configuration storage                         │  ││
│  │  │  Port: 5432                                      │  ││
│  │  └──────────────────────────────────────────────────┘  ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Installation Process

The [`setup-infra.sh`](setup-infra.sh) script orchestrates the installation:

1. **Download Components**
   - watsonx.data Developer Edition installer (tar)
   - HCD 1.2.5 distribution (zip)

2. **Prepare Configuration**
   - Create minimal `dev-config.yaml`
   - Configure resource limits
   - Set up storage paths

3. **Run Installer**
   - Installer creates Kind cluster
   - Deploys Helm charts
   - Configures networking
   - Initializes services

4. **Post-Installation**
   - Configure kubectl context
   - Set up port forwarding
   - Verify pod status

### Key Characteristics

- **Self-Contained**: All components run in containers
- **Isolated**: Separate Kubernetes namespace (`wxd`)
- **Persistent**: Data stored in host volumes (`/opt/wxd`)
- **Scalable**: Can add worker nodes (not used in demo)
- **Portable**: Can be backed up and restored

### Resource Allocation

```yaml
Presto:
  CPU: 2 cores
  Memory: 8GB
  
Minio:
  CPU: 1 core
  Memory: 2GB
  
Hive Metastore:
  CPU: 1 core
  Memory: 2GB
  
Console:
  CPU: 1 core
  Memory: 2GB
  
PostgreSQL:
  CPU: 0.5 cores
  Memory: 1GB
```

---

## HCD (IBM Cassandra) Integration

### What is HCD?

HCD (Hyperconverged Database) is IBM's distribution of Apache Cassandra, optimized for operational workloads. Unlike watsonx.data components, HCD runs as a **native systemd service** directly on the VM.

### Why Native Installation?

HCD is installed natively (not in Kubernetes) for several reasons:

1. **Performance**: Direct access to system resources
2. **Simplicity**: No container overhead
3. **Stability**: Proven systemd service management
4. **Integration**: Easier connection from host-based services
5. **Resource Control**: Direct memory and CPU allocation

### HCD Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HCD Service                           │
│                  (systemd managed)                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Cassandra Node (Single Node Cluster)              │ │
│  │                                                     │ │
│  │  Installation: /opt/hcd-1.2.5/                    │ │
│  │  Data: /opt/hcd-1.2.5/data/                       │ │
│  │  Logs: /opt/hcd-1.2.5/logs/                       │ │
│  │  Config: /opt/hcd-1.2.5/conf/cassandra.yaml       │ │
│  │                                                     │ │
│  │  Port: 9042 (CQL)                                  │ │
│  │  JMX Port: 7199                                    │ │
│  │                                                     │ │
│  │  Java: OpenJDK 11 (required by Cassandra)         │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### HCD Configuration

Key configuration in `/opt/hcd-1.2.5/conf/cassandra.yaml`:

```yaml
cluster_name: 'HCD Cluster'
listen_address: localhost
rpc_address: 0.0.0.0
native_transport_port: 9042

# Single node configuration
num_tokens: 256
endpoint_snitch: SimpleSnitch

# Memory settings
heap_size: 4G
```

### Schema Design

HCD stores operational data with TTL-based expiration:

```
Keyspace: affiliate_junction
  Replication: SimpleStrategy, RF=1

Tables:
  ┌─────────────────────────────────────────────────────┐
  │  impression_tracking (TTL: 5 minutes)               │
  │  - Partition: (publishers_id, cookie_id, adv_id)   │
  │  - Clustering: ts (TIMEUUID)                        │
  │  - Purpose: Raw impression events                   │
  └─────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────┐
  │  impressions_by_minute (TTL: 10 minutes)            │
  │  - Partition: (bucket_date, bucket)                 │
  │  - Clustering: ts (TIMEUUID)                        │
  │  - Purpose: Time-bucketed impressions               │
  └─────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────┐
  │  conversion_tracking (TTL: 5 minutes)               │
  │  - Partition: (publishers_id, cookie_id, adv_id)   │
  │  - Clustering: ts (TIMEUUID)                        │
  │  - Purpose: Raw conversion events                   │
  └─────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────┐
  │  publishers (No TTL)                                │
  │  - Partition: publishers_id                         │
  │  - Purpose: Aggregated publisher metrics            │
  └─────────────────────────────────────────────────────┘
  
  ┌─────────────────────────────────────────────────────┐
  │  advertisers (No TTL)                               │
  │  - Partition: advertisers_id                        │
  │  - Purpose: Aggregated advertiser metrics           │
  └─────────────────────────────────────────────────────┘
```

### HCD-Presto Integration

HCD is integrated with Presto via the Cassandra connector:

```
Presto Catalog: hcd
  Connector: cassandra
  Connection: localhost:9042
  Keyspace: affiliate_junction
  
Configuration: /opt/wxd/presto/catalog/hcd.properties
  connector.name=cassandra
  cassandra.contact-points=localhost
  cassandra.native-protocol-port=9042
```

This allows Presto to query HCD tables using SQL:
```sql
SELECT * FROM hcd.affiliate_junction.publishers;
```

---

## Data Flow Architecture

### End-to-End Data Pipeline

```
┌──────────────┐
│   Traffic    │  Generates synthetic impression & conversion events
│  Generator   │  Rate: ~5000 events/minute
└──────┬───────┘
       │ INSERT (CQL)
       ↓
┌──────────────┐
│     HCD      │  Stores operational data with TTL
│  (Cassandra) │  Retention: 5-10 minutes
└──────┬───────┘
       │ SELECT (via Spark-Cassandra connector)
       ↓
┌──────────────┐
│  hcd_to_     │  ETL: Reads from HCD, aggregates, writes to Iceberg
│  presto      │  Technology: PySpark
│  (ETL)       │  Frequency: Continuous (every minute)
└──────┬───────┘
       │ INSERT (via Spark-Iceberg)
       ↓
┌──────────────┐
│   Iceberg    │  Stores analytical data permanently
│   Tables     │  Format: Parquet files in Minio
│  (in Minio)  │  Retention: Unlimited
└──────┬───────┘
       │ SELECT (via Presto)
       ↓
┌──────────────┐
│  presto_to_  │  ETL: Calculates summaries, writes back to HCD
│  hcd         │  Technology: Python + Presto
│  (ETL)       │  Frequency: Continuous (every minute)
└──────┬───────┘
       │ INSERT (CQL)
       ↓
┌──────────────┐
│     HCD      │  Stores summary statistics (no TTL)
│  (Summary)   │  Tables: publishers, advertisers
└──────┬───────┘
       │ SELECT (CQL + Presto)
       ↓
┌──────────────┐
│   Web UI     │  Displays dashboards with federated queries
│  (FastAPI)   │  Queries both HCD and Iceberg via Presto
└──────────────┘
```

### Data Lifecycle

1. **Generation** (0-5 seconds)
   - Traffic generator creates events
   - Events written to HCD immediately
   - In-memory tracking for conversion attribution

2. **Operational Storage** (5-10 minutes)
   - Data stored in HCD with TTL
   - Available for real-time queries
   - Automatic expiration after TTL

3. **ETL Processing** (1-2 minutes)
   - hcd_to_presto reads recent data
   - Aggregates by time windows
   - Writes to Iceberg tables

4. **Analytical Storage** (Permanent)
   - Data stored in Iceberg format
   - Parquet files in Minio
   - Available for historical analysis

5. **Summary Calculation** (1-2 minutes)
   - presto_to_hcd queries Iceberg
   - Calculates aggregated metrics
   - Writes summaries back to HCD

6. **Visualization** (Real-time)
   - Web UI queries both sources
   - Federated queries via Presto
   - Real-time + historical views

---

## Application Components

### Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Services                      │
│                   (systemd managed)                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  generate_traffic.service                              │ │
│  │  - Python script                                       │ │
│  │  - Generates synthetic events                          │ │
│  │  - Writes to HCD                                       │ │
│  │  - Startup delay: 30s                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  hcd_to_presto.service                                 │ │
│  │  - PySpark application                                 │ │
│  │  - Reads from HCD                                      │ │
│  │  - Writes to Iceberg                                   │ │
│  │  - Startup delay: 60s                                  │ │
│  │  - Java 17 required                                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  presto_to_hcd.service                                 │ │
│  │  - Python + Presto                                     │ │
│  │  - Reads from Iceberg                                  │ │
│  │  - Writes to HCD                                       │ │
│  │  - Startup delay: 60s                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  presto_insights.service                               │ │
│  │  - Python + Presto                                     │ │
│  │  - Calculates analytics                                │ │
│  │  - Updates metrics                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  presto_cleanup.service                                │ │
│  │  - Python + Presto                                     │ │
│  │  - Manages data lifecycle                              │ │
│  │  - Cleans old data                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  uvicorn.service                                       │ │
│  │  - FastAPI application                                 │ │
│  │  - Web UI server                                       │ │
│  │  - Port: 10000                                         │ │
│  │  - Queries HCD and Presto                              │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Shared Libraries

All services use common modules from [`affiliate_common/`](affiliate_common/):

```python
affiliate_common/
├── __init__.py
├── database_connections.py    # CassandraConnection, PrestoConnection
├── schema_executor.py          # Schema initialization
└── services_manager.py         # Service monitoring & config
```

#### Key Features:
- **Query Metrics Capture**: All queries automatically tracked
- **Connection Pooling**: Reusable database connections
- **Error Handling**: Retry logic and graceful degradation
- **Configuration Management**: Dynamic settings via HCD
- **Monitoring**: Service health and performance metrics

### Web Application Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  main.py                                           │ │
│  │  - Application entry point                         │ │
│  │  - Route definitions                               │ │
│  │  - Authentication                                  │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Database Wrappers                                 │ │
│  │  - cassandra_wrapper.py (HCD queries)             │ │
│  │  - presto_wrapper.py (Presto queries)             │ │
│  │  - Query metrics capture                           │ │
│  │  - Thread-local storage                            │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Business Logic                                    │ │
│  │  - publishers.py (Publisher operations)           │ │
│  │  - advertisers.py (Advertiser operations)         │ │
│  │  - hcd_operations.py (HCD utilities)              │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Frontend                                          │ │
│  │  - templates/ (Jinja2 HTML)                       │ │
│  │  - assets/css/ (Stylesheets)                      │ │
│  │  - assets/js/ (JavaScript)                        │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Network Architecture

### Port Forwarding Strategy

Since watsonx.data runs in Kubernetes, services are not directly accessible from outside the cluster. We use **persistent port forwarding** via systemd services:

```
┌─────────────────────────────────────────────────────────┐
│                  Host Machine (VM)                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Port Forward Services (systemd)                   │ │
│  │                                                     │ │
│  │  presto-port-forward.service                       │ │
│  │    localhost:8443 → wxd/ibm-lh-presto-svc:8443   │ │
│  │                                                     │ │
│  │  wxd-ui-port-forward.service                       │ │
│  │    localhost:9443 → wxd/lhconsole-ui-svc:443     │ │
│  │                                                     │ │
│  │  minio-api-port-forward.service                    │ │
│  │    localhost:9000 → wxd/ibm-lh-minio-svc:9000    │ │
│  │                                                     │ │
│  │  minio-console-port-forward.service                │ │
│  │    localhost:9001 → wxd/ibm-lh-minio-svc:9001    │ │
│  │                                                     │ │
│  │  metastore-port-forward.service                    │ │
│  │    localhost:9083 → wxd/ibm-lh-mds-thrift:8381   │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Security Group (IBM Cloud Firewall)               │ │
│  │  - Allows inbound on ports: 22, 8443, 9000,       │ │
│  │    9001, 9083, 9443, 10000                         │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Connection Flow

```
External Client
    ↓
Floating IP:9443
    ↓
Security Group (Allow)
    ↓
VM:9443 (Port Forward Service)
    ↓
kubectl port-forward
    ↓
Kind Cluster
    ↓
wxd namespace
    ↓
lhconsole-ui-svc:443
    ↓
lhconsole-ui pod
```

See [`PORT_FORWARDS.md`](PORT_FORWARDS.md) for detailed port forwarding documentation.

---

## Storage Architecture

### Storage Layers

```
┌─────────────────────────────────────────────────────────┐
│                    Storage Architecture                  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  HCD Data (/opt/hcd-1.2.5/data/)                  │ │
│  │  - Operational data with TTL                       │ │
│  │  - SSTables (Sorted String Tables)                 │ │
│  │  - Commit logs                                     │ │
│  │  - Size: ~1-2GB (due to TTL)                       │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Iceberg Data (/opt/wxd/minio/)                   │ │
│  │  - Analytical data (permanent)                     │ │
│  │  - Parquet files                                   │ │
│  │  - Metadata files                                  │ │
│  │  - Size: Grows over time                           │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Metastore Data (/opt/wxd/postgres/)              │ │
│  │  - Table metadata                                  │ │
│  │  - Schema definitions                              │ │
│  │  - Catalog information                             │ │
│  │  - Size: ~100MB                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Application Data (/root/affiliate-junction-demo/)│ │
│  │  - Python code                                     │ │
│  │  - Configuration files                             │ │
│  │  - Logs                                            │ │
│  │  - Size: ~100MB                                    │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Data Formats

#### HCD (Cassandra)
- **Format**: SSTables (binary)
- **Compression**: LZ4
- **Indexing**: Bloom filters, partition indexes
- **Compaction**: Size-tiered compaction strategy

#### Iceberg
- **Format**: Parquet (columnar)
- **Compression**: Snappy
- **Partitioning**: By hour and publisher bucket
- **Metadata**: JSON manifest files

---

## Service Architecture

### Service Dependencies

```
System Boot
    ↓
Docker Service
    ↓
Kind Cluster
    ↓
watsonx.data Pods
    ↓
Port Forward Services
    ↓
HCD Service
    ↓
Application Services
```

### Service Startup Sequence

1. **System Boot** (0s)
   - Docker starts
   - Kind cluster auto-starts
   - watsonx.data pods initialize

2. **Port Forwards** (30s)
   - systemd services start
   - kubectl port-forward commands execute
   - Connections established

3. **HCD** (60s)
   - Cassandra starts
   - Schema initialized
   - Ready for connections

4. **Traffic Generator** (90s)
   - Waits for HCD
   - Starts generating events
   - Writes to HCD

5. **ETL Services** (120s)
   - Wait for HCD and Presto
   - Start processing data
   - Continuous operation

6. **Web UI** (120s)
   - Starts FastAPI server
   - Connects to HCD and Presto
   - Ready for requests

### Service Monitoring

All services report metrics to HCD `services` table:

```sql
CREATE TABLE services (
    service_name TEXT PRIMARY KEY,
    status TEXT,
    last_updated TIMESTAMP,
    stats TEXT,           -- JSON timeseries data
    settings TEXT,        -- JSON configuration
    query_metrics TEXT    -- JSON query performance
);
```

See [`SERVICES.md`](SERVICES.md) for detailed service documentation.

---

## Query Federation

### What is Query Federation?

Query federation allows Presto to execute a single SQL query across multiple data sources (HCD and Iceberg) without moving data.

### Federation Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Presto Coordinator                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Query Parser & Planner                            │ │
│  │  - Parses SQL                                      │ │
│  │  - Creates execution plan                          │ │
│  │  - Optimizes query                                 │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Connector Manager                                 │ │
│  │                                                     │ │
│  │  ┌──────────────┐         ┌──────────────┐        │ │
│  │  │ HCD Connector│         │Iceberg Conn. │        │ │
│  │  │              │         │              │        │ │
│  │  │ Catalog: hcd │         │Catalog: ice  │        │ │
│  │  └──────┬───────┘         └──────┬───────┘        │ │
│  │         │                        │                 │ │
│  └─────────┼────────────────────────┼────────────────┘ │
│            │                        │                  │
└────────────┼────────────────────────┼──────────────────┘
             │                        │
             ↓                        ↓
    ┌────────────────┐      ┌────────────────┐
    │      HCD       │      │    Iceberg     │
    │   (Cassandra)  │      │   (in Minio)   │
    └────────────────┘      └────────────────┘
```

### Federated Query Example

```sql
-- Query combining real-time (HCD) and historical (Iceberg) data
SELECT 
    h.publishers_id,
    h.publisher_name,
    h.total_impressions as current_impressions,
    i.total_impressions as historical_impressions,
    (h.total_impressions - i.total_impressions) as growth
FROM 
    hcd.affiliate_junction.publishers h
JOIN 
    iceberg_data.affiliate.publishers i
    ON h.publishers_id = i.publishers_id
WHERE 
    h.total_impressions > 1000
ORDER BY 
    growth DESC
LIMIT 10;
```

### Query Execution Flow

1. **Parse**: Presto parses SQL and identifies catalogs
2. **Plan**: Creates execution plan with connector-specific operations
3. **Pushdown**: Pushes predicates to each data source
4. **Execute**: Runs queries in parallel on both sources
5. **Merge**: Combines results in Presto
6. **Return**: Returns unified result set

### Performance Optimization

- **Predicate Pushdown**: WHERE clauses pushed to sources
- **Projection Pushdown**: Only requested columns retrieved
- **Partition Pruning**: Skips irrelevant partitions
- **Parallel Execution**: Queries run concurrently
- **Result Streaming**: Data streamed as available

---

## Summary

### Key Architectural Decisions

1. **Hybrid Deployment**
   - watsonx.data in Kubernetes (portable, scalable)
   - HCD native (performance, simplicity)
   - Best of both worlds

2. **TTL-Based Data Lifecycle**
   - Operational data expires automatically
   - No manual cleanup needed
   - Predictable storage usage

3. **Persistent Port Forwarding**
   - systemd services for reliability
   - Survives reboots and failures
   - Production-ready approach

4. **Federated Queries**
   - Single SQL interface
   - No data duplication
   - Real-time + historical analysis

5. **Service-Based Architecture**
   - Independent, manageable services
   - Clear separation of concerns
   - Easy to monitor and debug

### Related Documentation

- **[SERVICES.md](SERVICES.md)** - Detailed service documentation
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment guide
- **[PORT_FORWARDS.md](PORT_FORWARDS.md)** - Port forwarding setup
- **[README.md](README.md)** - Project overview
- **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)** - Demo walkthrough

---

## Diagrams

### Complete System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IBM Cloud VM                                    │
│                         (RHEL 9, 8 vCPU, 32GB RAM)                          │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    watsonx.data (Kubernetes - Kind)                     │ │
│  │                                                                         │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │ │
│  │  │  Presto  │  │  Minio   │  │   HMS    │  │ Console  │  │Postgres │ │ │
│  │  │  :8443   │  │:9000/9001│  │  :8381   │  │  :443    │  │  :5432  │ │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │ │
│  │       │             │             │             │             │       │ │
│  │       └─────────────┴─────────────┴─────────────┴─────────────┘       │ │
│  │                              ↓                                         │ │
│  │                    Port Forward Services                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                  ↓                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         Native Services                                 │ │
│  │                                                                         │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │ │
│  │  │   HCD    │→ │ Traffic  │→ │hcd_to_   │→ │presto_to │→ │ Web UI  │ │ │
│  │  │  :9042   │  │Generator │  │presto    │  │  _hcd    │  │ :10000  │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │ │
│  │       ↓              ↓              ↓              ↓            ↓       │ │
│  │  [Operational]  [Synthetic]    [ETL to]      [ETL from]   [Dashboard]  │ │
│  │   [Database]     [Events]      [Iceberg]     [Iceberg]    [Queries]    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  Data Flow: Traffic → HCD → ETL → Iceberg → ETL → HCD → Web UI             │
└─────────────────────────────────────────────────────────────────────────────┘
```

This architecture enables:
- **Real-time operational queries** via HCD
- **Historical analytical queries** via Iceberg
- **Federated queries** combining both sources
- **Automatic data lifecycle** via TTL and ETL
- **Complete observability** via query metrics