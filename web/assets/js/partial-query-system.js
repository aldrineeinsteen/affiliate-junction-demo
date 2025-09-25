/**
 * Query System Partial JavaScript
 * Handles the query monitoring panel functionality for query_panel.html partial
 * This provides reusable query tracking and panel management across pages
 */

// Query tracking state
let queryCounter = 0;
let totalResponseTime = 0;
let unreadQueryCount = 0;

/**
 * Initialize the query panel functionality
 * Should be called on DOMContentLoaded for each page
 */
function initializeQueryPanel() {
  const panel = document.getElementById('queryPanel');
  const toggleBtn = document.getElementById('queryPanelToggle');
  
  if (!panel || !toggleBtn) {
    console.warn('Query panel elements not found. Query panel initialization skipped.');
    return;
  }
  
  // Toggle panel on button click
  toggleBtn.addEventListener('click', function() {
    const isCurrentlyOpen = panel.classList.contains('open');
    
    panel.classList.toggle('open');
    
    // Update button tooltip and aria label
    if (isCurrentlyOpen) {
      toggleBtn.setAttribute('title', 'Show query panel');
      toggleBtn.setAttribute('aria-label', 'Show Query Panel');
    } else {
      toggleBtn.setAttribute('title', 'Hide query panel');
      toggleBtn.setAttribute('aria-label', 'Hide Query Panel');
      
      // Clear badge when panel is opened
      clearQueryBadge();
    }
  });
  
  // Close panel when clicking outside (optional)
  document.addEventListener('click', function(event) {
    const isClickInsidePanel = panel.contains(event.target);
    const isClickOnToggle = toggleBtn.contains(event.target);
    
    if (!isClickInsidePanel && !isClickOnToggle && panel.classList.contains('open')) {
      // Uncomment the lines below if you want to close on outside click
      // panel.classList.remove('open');
      // toggleBtn.setAttribute('title', 'Show query panel');
      // toggleBtn.setAttribute('aria-label', 'Show Query Panel');
    }
  });
}

/**
 * Add a new query to the monitoring panel
 * @param {string} method - HTTP method (GET, POST, etc.)
 * @param {string} url - Request URL
 * @param {string} status - Query status (pending, success, error)
 * @param {Array} queryMetrics - Optional array of query metrics from server
 * @returns {string} queryId - Unique ID for this query
 */
function addQueryToPanel(method, url, status = 'pending', queryMetrics = null) {
  const queryList = document.getElementById('queryList');
  const noQueries = document.getElementById('noQueries');
  
  if (!queryList) {
    console.warn('Query list element not found. Cannot add query to panel.');
    return null;
  }
  
  // Hide "no queries" message
  if (noQueries) {
    noQueries.style.display = 'none';
  }
  
  queryCounter++;
  const queryId = `query-${Date.now()}-${queryCounter}`;
  const timestamp = new Date().toLocaleTimeString();
  
  // Create query item
  const queryItem = document.createElement('div');
  queryItem.className = `query-item ${status}`;
  queryItem.id = queryId;
  
  // If we have query metrics, show database queries
  if (queryMetrics && queryMetrics.length > 0) {
    let queriesHtml = '';
    queryMetrics.forEach(query => {
      const queryType = query.query_type || 'Unknown';
      const queryTypeClass = queryType.toLowerCase();
      const executionTime = query.execution_time_ms ? `${Math.round(query.execution_time_ms)}ms` : 'N/A';
      const description = query.query_description || 'Database query';
      
      queriesHtml += `
        <div class="query-item-container">
          <div class="query-item-header">
            <span class="query-type-badge ${queryTypeClass}">${queryType}</span>
            <span class="query-execution-time">${executionTime}</span>
            <span class="query-item-time mx-2">${timestamp}</span>
          </div>
          <div class="query-item-url">${url}</div>
          <div class="query-item-description">${description}</div>
        </div>
      `;
    });
    queryItem.innerHTML = queriesHtml;
  } else {
    // Fallback to HTTP request display
    queryItem.innerHTML = `
      <div class="query-item-container">
        <div class="query-item-header">
          <span class="query-type-badge http">${method}</span>
          <span class="query-execution-time" id="${queryId}-time">Executing...</span>
          <span class="query-item-time mx-2">${timestamp}</span>
        </div>
        <div class="query-item-url">${url}</div>
        <div class="query-item-response">
          <span id="${queryId}-response">Executing...</span>
        </div>
      </div>
    `;
  }
  
  // Add to top of list
  queryList.insertBefore(queryItem, queryList.firstChild);
  
  // Update counters
  updateQueryStats();
  
  // Increment badge count for new queries
  incrementQueryBadge();
  
  // Return query ID for later updates
  return queryId;
}

/**
 * Update the status of an existing query
 * @param {string} queryId - The query ID returned from addQueryToPanel
 * @param {string} status - New status (success, error, etc.)
 * @param {number} responseTime - Response time in milliseconds
 * @param {string} details - Additional details to display
 */
function updateQueryStatus(queryId, status, responseTime = null, details = null) {
  const queryItem = document.getElementById(queryId);
  if (!queryItem) return;
  
  // Update status class and text
  queryItem.className = `query-item ${status}`;
  const statusSpan = queryItem.querySelector('.query-item-status');
  if (statusSpan) {
    statusSpan.className = `query-item-status ${status}`;
    statusSpan.textContent = status.toUpperCase();
  }
  
  // Update response details
  const responseSpan = document.getElementById(`${queryId}-response`);
  if (responseSpan) {
    let responseText = '';
    if (responseTime !== null) {
      responseText = `${responseTime}ms`;
      totalResponseTime += responseTime;
    }
    if (details) {
      responseText += ` • ${details}`;
    }
    if (status === 'error') {
      responseText = details || 'Request failed';
    }
    responseSpan.textContent = responseText;
  }
  
  updateQueryStats();
}

/**
 * Update the query statistics display
 */
function updateQueryStats() {
  const totalQueriesEl = document.getElementById('totalQueries');
  const avgResponseTimeEl = document.getElementById('avgResponseTime');
  
  if (totalQueriesEl) {
    totalQueriesEl.textContent = queryCounter;
  }
  
  if (avgResponseTimeEl) {
    const avgTime = queryCounter > 0 ? Math.round(totalResponseTime / queryCounter) : 0;
    avgResponseTimeEl.textContent = `${avgTime}ms`;
  }
}

/**
 * Update the query badge display
 */
function updateQueryBadge() {
  const badge = document.getElementById('queryBadge');
  const panel = document.getElementById('queryPanel');
  
  if (!badge || !panel) return;
  
  if (unreadQueryCount > 0 && !panel.classList.contains('open')) {
    badge.textContent = unreadQueryCount;
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

/**
 * Increment the unread query count
 */
function incrementQueryBadge() {
  const panel = document.getElementById('queryPanel');
  // Only increment if panel is closed
  if (panel && !panel.classList.contains('open')) {
    unreadQueryCount++;
    updateQueryBadge();
  }
}

/**
 * Clear the query badge count
 */
function clearQueryBadge() {
  unreadQueryCount = 0;
  updateQueryBadge();
}

/**
 * Enhanced fetch wrapper that automatically tracks all API requests
 * This replaces the global fetch function to provide automatic query monitoring
 */
function initializeEnhancedFetch() {
  // Store the original fetch function
  const originalFetch = window.fetch;
  
  // Replace the global fetch function
  window.fetch = function(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const startTime = Date.now();
    
    return originalFetch(url, options)
      .then(response => {
        const responseTime = Date.now() - startTime;
        const status = response.ok ? 'success' : 'error';
        
        // Clone the response to read it without consuming it
        return response.clone().json().then(data => {
          let queryId;
          
          // If the response contains query_metrics, display those
          if (data && data.query_metrics && data.query_metrics.length > 0) {
            queryId = addQueryToPanel(method, url, status, data.query_metrics);
          } else {
            // Fallback to HTTP request tracking
            queryId = addQueryToPanel(method, url, status);
            const details = response.ok ? `${response.status} OK` : `${response.status} ${response.statusText}`;
            updateQueryStatus(queryId, status, responseTime, details);
          }
          
          return response;
        }).catch(() => {
          // If JSON parsing fails, fallback to HTTP request tracking
          const queryId = addQueryToPanel(method, url, status);
          const details = response.ok ? `${response.status} OK` : `${response.status} ${response.statusText}`;
          updateQueryStatus(queryId, status, responseTime, details);
          return response;
        });
      })
      .catch(error => {
        const responseTime = Date.now() - startTime;
        const queryId = addQueryToPanel(method, url, 'error');
        updateQueryStatus(queryId, 'error', responseTime, error.message);
        throw error;
      });
  };
}

/**
 * Initialize the complete query system for the query panel
 * Call this function to set up query monitoring
 */
function initializeQuerySystemPartial() {
  initializeQueryPanel();
  initializeEnhancedFetch();
}

// Auto-initialize if DOM is already loaded, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeQuerySystemPartial);
} else {
  initializeQuerySystemPartial();
}