/**
 * Query System Partial JavaScript
 * Handles the query monitoring panel functionality for query_panel.html partial
 * This provides reusable query tracking and panel management across pages
 */

// Query tracking state
let hcdQueryCount = 0;
let prestoQueryCount = 0;
let unreadQueryCount = 0;

// Store detailed query data for the details panel
let queryDataStore = new Map();

// Track the currently active query
let activeQueryId = null;

// Track which queries have been read (clicked) vs new
let readQueries = new Set();

/**
 * Initialize the query panel functionality
 * Should be called on DOMContentLoaded for each page
 */
function initializeQueryPanel() {
  const panel = document.getElementById('queryPanel');
  const toggleBtn = document.getElementById('queryPanelToggle');
  const clearBtn = document.getElementById('clearQueriesBtn');
  const modalOverlay = document.getElementById('queryModalOverlay');
  
  if (!panel || !toggleBtn) {
    console.warn('Query panel elements not found. Query panel initialization skipped.');
    return;
  }
  
  // Toggle panel on button click
  toggleBtn.addEventListener('click', function() {
    const isCurrentlyOpen = panel.classList.contains('open');
    
    panel.classList.toggle('open');
    
    // Show/hide modal overlay
    if (modalOverlay) {
      if (isCurrentlyOpen) {
        hideModalOverlay();
      } else {
        showModalOverlay();
      }
    }
    
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
  
  // Clear queries button click
  if (clearBtn) {
    clearBtn.addEventListener('click', function() {
      resetQueryCounters();
    });
  }
  
  // Close panel when clicking on modal overlay
  if (modalOverlay) {
    modalOverlay.addEventListener('click', function() {
      closePanels();
    });
  }
  
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
  
  // Initialize query details panel
  initializeQueryDetailsPanel();
  
  // Initialize keyboard event handlers
  initializeKeyboardHandlers();
}

/**
 * Initialize keyboard event handlers for the query system
 */
function initializeKeyboardHandlers() {
  document.addEventListener('keydown', function(event) {
    // Handle ESC key press
    if (event.key === 'Escape') {
      const queryPanel = document.getElementById('queryPanel');
      const queryDetailsPanel = document.getElementById('queryDetailsPanel');
      
      // Close query details panel first if it's open
      if (queryDetailsPanel && queryDetailsPanel.classList.contains('open')) {
        hideQueryDetails();
        event.preventDefault();
        return;
      }
      
      // Close query panel if it's open
      if (queryPanel && queryPanel.classList.contains('open')) {
        closePanels();
        event.preventDefault();
        return;
      }
    }
  });
}

/**
 * Initialize the query details panel functionality
 */
function initializeQueryDetailsPanel() {
  const detailsPanel = document.getElementById('queryDetailsPanel');
  const closeBtn = document.getElementById('closeQueryDetailsBtn');
  
  if (!detailsPanel) {
    console.warn('Query details panel elements not found. Details panel initialization skipped.');
    return;
  }
  
  // Close button click
  if (closeBtn) {
    closeBtn.addEventListener('click', function() {
      hideQueryDetails();
    });
  }
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
  
  const queryId = `query-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  const now = new Date();
  const timestamp = now.toLocaleTimeString() + '.' + String(now.getMilliseconds()).padStart(3, '0');
  
  // If we have query metrics, create individual query items instead of grouping them
  if (queryMetrics && queryMetrics.length > 0) {
    // For multiple queries (like services), create separate query items for each
    const queryIds = [];
    
    queryMetrics.forEach((query, index) => {
      const queryType = query.query_type || 'Unknown';
      const queryTypeClass = queryType.toLowerCase();
      const executionTime = query.execution_time_ms ? `${Math.round(query.execution_time_ms)}ms` : 'N/A';
      const description = query.query_description || 'Database query';
      
      // Create unique ID for this individual query
      const individualQueryId = `query-${Date.now()}-${Math.random().toString(36).substr(2, 9)}-${index}`;
      queryIds.push(individualQueryId);
      
      // Store detailed query data for the details panel
      queryDataStore.set(individualQueryId, {
        description: description,
        formatted_query_text: query.formatted_query_text || 'Query text not available',
        parameters: query.parameters || [],
        rowsReturned: query.rows_returned || 0,
        rowsData: query.rows_data || [],
        executionTime: executionTime,
        queryType: queryType,
        timestamp: timestamp,
        url: url
      });
      
      // Update query engine counters
      if (queryType.toLowerCase() === 'hcd') {
        hcdQueryCount++;
      } else if (queryType.toLowerCase() === 'presto') {
        prestoQueryCount++;
      }
      
      // Create individual query item element
      const individualQueryItem = document.createElement('div');
      individualQueryItem.className = `query-item ${status} new`;
      individualQueryItem.id = individualQueryId;
      
      individualQueryItem.innerHTML = `
        <div class="query-item-container" onclick="showQueryDetails('${individualQueryId}')" style="cursor: pointer;">
          <div class="query-item-header">
            <span class="query-type-badge ${queryTypeClass}">${queryType}</span>
            <span class="query-execution-time">${executionTime}</span>
            <span class="query-item-time mx-2">${timestamp}</span>
          </div>
          <div class="query-item-description">${description}</div>
          <div class="query-item-url">${url}</div>
        </div>
      `;
      
      // Add individual query item to top of list
      queryList.insertBefore(individualQueryItem, queryList.firstChild);
      
      // Increment badge count for each new query
      incrementQueryBadge();
    });
    
    // Update stats and return the first query ID for compatibility
    updateQueryStats();
    return queryIds[0] || queryId;
  } else {
    // No query metrics - do not add to panel or update badge
    return null;
  }
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
  const hcdQueryCountEl = document.getElementById('hcdQueryCount');
  const prestoQueryCountEl = document.getElementById('prestoQueryCount');
  
  if (hcdQueryCountEl) {
    hcdQueryCountEl.textContent = hcdQueryCount;
  }
  
  if (prestoQueryCountEl) {
    prestoQueryCountEl.textContent = prestoQueryCount;
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
 * Reset all query counters
 */
function resetQueryCounters() {
  hcdQueryCount = 0;
  prestoQueryCount = 0;
  unreadQueryCount = 0;
  
  // Clear active state and query data
  clearActiveQueryState();
  queryDataStore.clear();
  readQueries.clear();
  
  // Clear the query list
  const queryList = document.getElementById('queryList');
  const noQueries = document.getElementById('noQueries');
  
  if (queryList) {
    // Remove all query items but keep the no-queries message
    const queryItems = queryList.querySelectorAll('.query-item');
    queryItems.forEach(item => item.remove());
    
    // Show the no-queries message
    if (noQueries) {
      noQueries.style.display = 'block';
    }
  }
  
  // Hide details panel when clearing
  hideQueryDetails();
  
  updateQueryStats();
  updateQueryBadge();
}

// Make resetQueryCounters available globally for services.js
window.resetQueryCounters = resetQueryCounters;

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
            
            // Update stats after processing metrics
            updateQueryStats();
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
 * Generate HTML table for row data
 * @param {Array} rowsData - Array of row objects 
 * @returns {string} HTML string for the table
 */
function generateRowDataTable(rowsData) {
  if (!rowsData || rowsData.length === 0) {
    return '<div class="text-muted">No sample rows provided</div>';
  }
  
  // Get all unique column names from all rows
  const allColumns = new Set();
  rowsData.forEach(row => {
    if (row && typeof row === 'object') {
      Object.keys(row).forEach(key => allColumns.add(key));
    }
  });
  
  const columns = Array.from(allColumns).sort();
  
  if (columns.length === 0) {
    return '<div class="text-muted">No column data available</div>';
  }
  
  let tableHtml = `
    <div class="table-responsive">
      <table class="table table-sm table-striped">
        <thead class="table-dark">
          <tr>`;
  
  // Add header columns
  columns.forEach(column => {
    tableHtml += `<th scope="col">${column}</th>`;
  });
  
  tableHtml += `
          </tr>
        </thead>
        <tbody>`;
  
  // Add data rows
  rowsData.forEach((row, rowIndex) => {
    tableHtml += '<tr>';
    columns.forEach(column => {
      let cellValue = '';
      if (row && typeof row === 'object' && row.hasOwnProperty(column)) {
        cellValue = row[column];
        // Handle null values
        if (cellValue === null || cellValue === undefined) {
          cellValue = '<span class="text-muted">null</span>';
        } else {
          // Escape HTML and wrap in spans for styling
          cellValue = String(cellValue).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
      } else {
        cellValue = '<span class="text-muted">-</span>';
      }
      tableHtml += `<td>${cellValue}</td>`;
    });
    tableHtml += '</tr>';
  });
  
  tableHtml += `
        </tbody>
      </table>
    </div>`;
  
  return tableHtml;
}

/**
 * Show the query details panel with information for a specific query
 * @param {string} queryId - The ID of the query to show details for
 */
function showQueryDetails(queryId) {
  const queryData = queryDataStore.get(queryId);
  if (!queryData) {
    console.warn('Query data not found for ID:', queryId);
    return;
  }
  
  // Mark this query as read
  readQueries.add(queryId);
  
  // Find the query item that contains this specific query and update its class
  const queryItems = document.querySelectorAll('.query-item');
  queryItems.forEach(item => {
    // Check if this item contains our target query
    const containers = item.querySelectorAll('.query-item-container[onclick*="' + queryId + '"]');
    if (containers.length > 0) {
      // Remove 'new' class and add 'read' class
      item.classList.remove('new');
      item.classList.add('read');
    }
  });
  
  // Clear previous active state
  clearActiveQueryState();
  
  // Set new active state
  setActiveQueryState(queryId);
  
  const detailsPanel = document.getElementById('queryDetailsPanel');
  const detailsContent = document.getElementById('queryDetailsContent');
  const detailsTitle = document.getElementById('queryDetailsTitle');
  const detailsSubtitle = document.getElementById('queryDetailsSubtitle');
  
  if (!detailsPanel || !detailsContent) {
    console.warn('Query details panel elements not found.');
    return;
  }
  
  // Update header
  if (detailsTitle) {
    detailsTitle.innerHTML = `${queryData.description}`;
  }
  if (detailsSubtitle) {
    detailsSubtitle.innerHTML = `<span class="query-type-badge ${queryData.queryType.toLowerCase()}">${queryData.queryType}</span> • ${queryData.timestamp} • ${queryData.executionTime}`;
  }
  
  // Format parameters for display
  let parametersHtml = 'None';
  if (queryData.parameters && queryData.parameters.length > 0) {
    parametersHtml = queryData.parameters.map(param => {
      if (typeof param === 'object') {
        return `<code>${JSON.stringify(param)}</code>`;
      }
      return `<code>${String(param)}</code>`;
    }).join(', ');
  }
  
  // Create details content HTML
  detailsContent.innerHTML = `
    <div class="query-details-section">
      <h6 class="query-details-section-title">
        <i class="bi bi-file-text me-2"></i>Query
      </h6>
      <div class="query-details-box p-09">
        <pre><code class="language-sql">${queryData.formatted_query_text}</code></pre>
      </div>
    </div>
    
    <div class="query-details-section">
      <h6 class="query-details-section-title">
        <i class="bi bi-gear me-2"></i>Parameters
      </h6>
      <div class="query-details-box">
        <div class="query-parameters">${parametersHtml}</div>
      </div>
    </div>
    
    <div class="query-details-section">
      <h6 class="query-details-section-title">
        <i class="bi bi-table me-2"></i>Results - ${queryData.rowsReturned.toLocaleString()} Rows Returned
      </h6>
      ${queryData.rowsReturned > 0 ? `
        <div class="mt-3">
          ${generateRowDataTable(queryData.rowsData)}
        </div>
      ` : ''}
    </div>
    
    <div class="query-details-section">
      <h6 class="query-details-section-title">
        <i class="bi bi-info-circle me-2"></i>Metadata
      </h6>
      <div class="query-details-metadata">
        <div class="query-details-row-info">
          <span class="query-details-label">Request URL:</span>
          <span class="query-details-value"><code>${queryData.url}</code></span>
        </div>
        <div class="query-details-row-info">
          <span class="query-details-label">Execution Time:</span>
          <span class="query-details-value">${queryData.executionTime}</span>
        </div>
        <div class="query-details-row-info">
          <span class="query-details-label">Query Type:</span>
          <span class="query-details-value"><span class="query-type-badge ${queryData.queryType.toLowerCase()}">${queryData.queryType}</span></span>
        </div>
      </div>
    </div>
  `;
  
  // Show the panel
  detailsPanel.classList.add('open');
  
  // Show modal overlay if not already shown
  const modalOverlay = document.getElementById('queryModalOverlay');
  if (modalOverlay) {
    showModalOverlay();
  }
  
  // Trigger Prism.js syntax highlighting if available
  if (typeof Prism !== 'undefined' && Prism.highlightAll) {
    // Use setTimeout to ensure DOM is updated before highlighting
    setTimeout(() => {
      Prism.highlightAll();
      // Remove all backgrounds from Prism-generated elements in query details
      const queryDetailsBox = detailsContent.querySelector('.query-details-box');
      if (queryDetailsBox) {
        // Remove background from all elements within the query box
        const allElements = queryDetailsBox.querySelectorAll('*');
        allElements.forEach(element => {
          element.style.background = 'none';
          element.style.backgroundColor = 'transparent';
        });
        // Also remove from pre and code specifically
        const preElements = queryDetailsBox.querySelectorAll('pre');
        const codeElements = queryDetailsBox.querySelectorAll('code');
        [...preElements, ...codeElements].forEach(element => {
          element.style.background = 'none';
          element.style.backgroundColor = 'transparent';
        });
      }
    }, 0);
  }
}

/**
 * Hide the query details panel
 */
function hideQueryDetails() {
  const detailsPanel = document.getElementById('queryDetailsPanel');
  if (detailsPanel) {
    detailsPanel.classList.remove('open');
  }
  
  // Hide modal overlay if both panels are closed
  const queryPanel = document.getElementById('queryPanel');
  const modalOverlay = document.getElementById('queryModalOverlay');
  
  if (modalOverlay && (!queryPanel || !queryPanel.classList.contains('open'))) {
    hideModalOverlay();
  }
  
  // Clear active state when hiding details
  clearActiveQueryState();
}

/**
 * Set the active query state
 * @param {string} queryId - The ID of the query to mark as active
 */
function setActiveQueryState(queryId) {
  activeQueryId = queryId;
  
  // Find the query item that contains this specific query
  const queryItems = document.querySelectorAll('.query-item');
  queryItems.forEach(item => {
    // Check if this item contains our target query
    const containers = item.querySelectorAll('.query-item-container[onclick*="' + queryId + '"]');
    if (containers.length > 0) {
      item.classList.add('active');
    }
  });
}

/**
 * Clear the active query state from all queries
 */
function clearActiveQueryState() {
  activeQueryId = null;
  
  // Remove active class from all query items
  const queryItems = document.querySelectorAll('.query-item');
  queryItems.forEach(item => {
    item.classList.remove('active');
  });
}

/**
 * Show the modal overlay
 */
function showModalOverlay() {
  const modalOverlay = document.getElementById('queryModalOverlay');
  if (modalOverlay) {
    modalOverlay.classList.add('show');
  }
}

/**
 * Hide the modal overlay
 */
function hideModalOverlay() {
  const modalOverlay = document.getElementById('queryModalOverlay');
  if (modalOverlay) {
    modalOverlay.classList.remove('show');
  }
}

/**
 * Close all query panels and hide modal overlay
 */
function closePanels() {
  const queryPanel = document.getElementById('queryPanel');
  const queryDetailsPanel = document.getElementById('queryDetailsPanel');
  const toggleBtn = document.getElementById('queryPanelToggle');
  
  // Close query panel
  if (queryPanel) {
    queryPanel.classList.remove('open');
  }
  
  // Close details panel
  if (queryDetailsPanel) {
    queryDetailsPanel.classList.remove('open');
  }
  
  // Update toggle button
  if (toggleBtn) {
    toggleBtn.setAttribute('title', 'Show query panel');
    toggleBtn.setAttribute('aria-label', 'Show Query Panel');
  }
  
  // Hide modal overlay
  hideModalOverlay();
  
  // Clear active state
  clearActiveQueryState();
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