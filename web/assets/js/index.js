/**
 * Index Page JavaScript
 * Handles affiliate junction demo functionality and API demonstrations
 */

/**
 * Handle analytics demo button click to showcase live affiliate data
 */
async function handleAnalyticsButtonClick() {
  const responseEl = document.getElementById("response");
  const fetchBtn = document.getElementById("fetchBtn");
  
  // Show loading state
  if (fetchBtn) {
    fetchBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading Analytics...';
    fetchBtn.disabled = true;
  }
  
  if (responseEl) {
    responseEl.classList.add("show");
    responseEl.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin me-2"></i>Fetching live affiliate data...</div>';
  }

  try {
    // Try to fetch from multiple demo endpoints to showcase the system
    const [apiData, publishersData, advertisersData] = await Promise.allSettled([
      fetch("/api").then(res => res.json()),
      fetch("/api/publishers/summary").then(res => res.ok ? res.json() : null).catch(() => null),
      fetch("/api/advertisers/summary").then(res => res.ok ? res.json() : null).catch(() => null)
    ]);

    let demoContent = `
      <div class="demo-results">
        <h5 class="mb-4"><i class="fas fa-chart-line me-2"></i>Live Affiliate Marketing Analytics</h5>
    `;

    // Show system status
    if (apiData.status === 'fulfilled') {
      demoContent += `
        <div class="demo-section-card mb-4">
          <h6><i class="fas fa-server me-2"></i>System Status</h6>
          <pre class="demo-json">${JSON.stringify(apiData.value, null, 2)}</pre>
        </div>
      `;
    }

    // Show publishers data if available
    if (publishersData.status === 'fulfilled' && publishersData.value) {
      demoContent += `
        <div class="demo-section-card mb-4">
          <h6><i class="fas fa-globe me-2"></i>Publishers Overview</h6>
          <pre class="demo-json">${JSON.stringify(publishersData.value, null, 2)}</pre>
        </div>
      `;
    }

    // Show advertisers data if available
    if (advertisersData.status === 'fulfilled' && advertisersData.value) {
      demoContent += `
        <div class="demo-section-card mb-4">
          <h6><i class="fas fa-bullhorn me-2"></i>Advertisers Overview</h6>
          <pre class="demo-json">${JSON.stringify(advertisersData.value, null, 2)}</pre>
        </div>
      `;
    }

    // Add data flow demonstration
    demoContent += `
        <div class="demo-section-card mb-4">
          <h6><i class="fas fa-database me-2"></i>Data Pipeline Status</h6>
          <div class="pipeline-status">
            <div class="pipeline-step">
              <i class="fas fa-check-circle text-success me-2"></i>
              <span>HCD (Cassandra) - Real-time data active</span>
            </div>
            <div class="pipeline-step">
              <i class="fas fa-arrow-right text-primary me-2"></i>
              <span>ETL Pipeline - Processing affiliate events</span>
            </div>
            <div class="pipeline-step">
              <i class="fas fa-chart-bar text-info me-2"></i>
              <span>Presto/Iceberg - Analytics ready</span>
            </div>
          </div>
        </div>
      `;

    demoContent += `
        <div class="demo-actions mt-4">
          <div class="row">
            <div class="col-md-6 mb-3">
              <a href="/publishers" class="btn btn-outline-primary btn-sm w-100">
                <i class="fas fa-globe me-2"></i>Publisher Dashboard
              </a>
            </div>
            <div class="col-md-6 mb-3">
              <a href="/advertisers" class="btn btn-outline-success btn-sm w-100">
                <i class="fas fa-bullhorn me-2"></i>Advertiser Dashboard
              </a>
            </div>
          </div>
        </div>
      </div>
    `;

    if (responseEl) {
      responseEl.innerHTML = demoContent;
    }

  } catch (error) {
    console.error("Error fetching demo data:", error);
    if (responseEl) {
      responseEl.innerHTML = `
        <div class="alert alert-warning">
          <h6><i class="fas fa-exclamation-triangle me-2"></i>Demo Data Unavailable</h6>
          <p>The affiliate marketing data pipeline may still be initializing. This demo showcases:</p>
          <ul class="mb-0">
            <li>Real-time affiliate tracking via HCD (Cassandra)</li>
            <li>Historical analytics via Presto/Iceberg</li>
            <li>Federated query capabilities across data sources</li>
            <li>Publisher and advertiser performance dashboards</li>
          </ul>
        </div>
      `;
    }
  } finally {
    // Reset button state
    if (fetchBtn) {
      fetchBtn.innerHTML = '<i class="fas fa-chart-line me-2"></i>View Live Analytics';
      fetchBtn.disabled = false;
    }
  }
}

/**
 * Handle services button click to show system status
 */
function handleServicesButtonClick() {
  window.location.href = '/services';
}

/**
 * Initialize the index page
 */
function initializeIndexPage() {
  // Set up analytics demo button
  const fetchBtn = document.getElementById("fetchBtn");
  if (fetchBtn) {
    fetchBtn.addEventListener("click", handleAnalyticsButtonClick);
  }

  // Set up services button
  const servicesBtn = document.getElementById("servicesBtn");
  if (servicesBtn) {
    servicesBtn.addEventListener("click", handleServicesButtonClick);
  }

  // Add some visual enhancements
  addVisualEnhancements();
}

/**
 * Add visual enhancements to the page
 */
function addVisualEnhancements() {
  // Add CSS for demo result styling
  const style = document.createElement('style');
  style.textContent = `
    .demo-results h5 {
      color: #2c3e50;
      border-bottom: 2px solid #667eea;
      padding-bottom: 0.5rem;
    }
    
    .demo-section-card {
      background: white;
      border: 1px solid #dee2e6;
      border-radius: 8px;
      padding: 1.5rem;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }
    
    .demo-section-card h6 {
      color: #495057;
      margin-bottom: 1rem;
      font-weight: 600;
    }
    
    .demo-json {
      background: #f8f9fa;
      border: 1px solid #dee2e6;
      border-radius: 4px;
      padding: 1rem;
      font-size: 0.85rem;
      max-height: 200px;
      overflow-y: auto;
      margin: 0;
    }
    
    .pipeline-status {
      padding: 1rem 0;
    }
    
    .pipeline-step {
      display: flex;
      align-items: center;
      margin-bottom: 0.75rem;
      padding: 0.5rem;
      background: #f8f9fa;
      border-radius: 6px;
      font-size: 0.95rem;
    }
    
    .demo-actions .btn {
      transition: all 0.3s ease;
    }
    
    .demo-actions .btn:hover {
      transform: translateY(-2px);
    }
  `;
  document.head.appendChild(style);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeIndexPage);
} else {
  initializeIndexPage();
}