/**
 * Sidebar Partial JavaScript
 * Handles the advertiser and publisher dropdown functionality for sidebar.html partial
 * This provides reusable sidebar functionality across pages
 */

/**
 * Load advertisers into the dropdown
 */
async function loadAdvertisers() {
  try {
    const response = await fetch("/api/advertisers");
    const data = await response.json();
    
    const select = document.getElementById("advertisersSelect");
    
    if (!select) {
      console.warn('Advertisers select element not found');
      return;
    }
    
    if (data.advertisers && data.advertisers.length > 0) {
      // Clear loading message
      select.innerHTML = '<option value="">Select an advertiser...</option>';
      
      // Add advertisers to dropdown
      data.advertisers.forEach(advertiser => {
        const option = document.createElement("option");
        option.value = advertiser.advertiser_id;
        option.textContent = advertiser.name;
        
        // Select current advertiser if it matches the page context (for dashboard page)
        const currentAdvertiserId = getCurrentAdvertiserId();
        if (advertiser.advertiser_id === currentAdvertiserId) {
          option.selected = true;
        }
        
        select.appendChild(option);
      });
    } else {
      select.innerHTML = '<option value="">No advertisers available</option>';
    }
  } catch (error) {
    console.error("Error loading advertisers:", error);
    const select = document.getElementById("advertisersSelect");
    if (select) {
      select.innerHTML = '<option value="">Error loading advertisers</option>';
    }
  }
}

/**
 * Load publishers into the dropdown
 */
async function loadPublishers() {
  try {
    const response = await fetch("/api/publishers");
    const data = await response.json();
    
    const select = document.getElementById("publishersSelect");
    
    if (!select) {
      console.warn('Publishers select element not found');
      return;
    }
    
    if (data.publishers && data.publishers.length > 0) {
      // Clear loading message
      select.innerHTML = '<option value="">Select a publisher...</option>';
      
      // Add publishers to dropdown
      data.publishers.forEach(publisher => {
        const option = document.createElement("option");
        option.value = publisher.publisher_id;
        option.textContent = publisher.name;
        
        // Select current publisher if it matches the page context (for dashboard page)
        const currentPublisherId = getCurrentPublisherId();
        if (publisher.publisher_id === currentPublisherId) {
          option.selected = true;
        }
        
        select.appendChild(option);
      });
    } else {
      select.innerHTML = '<option value="">No publishers available</option>';
    }
  } catch (error) {
    console.error("Error loading publishers:", error);
    const select = document.getElementById("publishersSelect");
    if (select) {
      select.innerHTML = '<option value="">Error loading publishers</option>';
    }
  }
}

/**
 * Get the current advertiser ID from the page context
 * This will try multiple methods: from data attribute, URL, or global variable
 */
function getCurrentAdvertiserId() {
  // Method 1: Try to get from a data attribute on body
  const bodyEl = document.body;
  if (bodyEl && bodyEl.dataset.advertiserId) {
    return bodyEl.dataset.advertiserId;
  }
  
  // Method 2: Try to get from a global variable (set by template)
  if (typeof window.ADVERTISER_ID !== 'undefined') {
    return window.ADVERTISER_ID;
  }
  
  // Method 3: Extract from URL path /advertiser/{id}
  const pathParts = window.location.pathname.split('/');
  if (pathParts[1] === 'advertiser' && pathParts[2]) {
    return pathParts[2];
  }
  
  return null;
}

/**
 * Get the current publisher ID from the page context
 * This will try multiple methods: from data attribute, URL, or global variable
 */
function getCurrentPublisherId() {
  // Method 1: Try to get from a data attribute on body
  const bodyEl = document.body;
  if (bodyEl && bodyEl.dataset.publisherId) {
    return bodyEl.dataset.publisherId;
  }
  
  // Method 2: Try to get from a global variable (set by template)
  if (typeof window.PUBLISHER_ID !== 'undefined') {
    return window.PUBLISHER_ID;
  }
  
  // Method 3: Extract from URL path /publisher/{id}
  const pathParts = window.location.pathname.split('/');
  if (pathParts[1] === 'publisher' && pathParts[2]) {
    return pathParts[2];
  }
  
  return null;
}

/**
 * Handle advertiser selection change
 */
function onAdvertiserChange() {
  const select = document.getElementById("advertisersSelect");
  if (!select) return;
  
  const selectedAdvertiser = select.value;
  
  if (selectedAdvertiser) {
    // Navigate to the advertiser dashboard page
    window.location.href = `/advertiser/${selectedAdvertiser}`;
  }
}

/**
 * Handle publisher selection change
 */
function onPublisherChange() {
  const select = document.getElementById("publishersSelect");
  if (!select) return;
  
  const selectedPublisher = select.value;
  
  if (selectedPublisher) {
    // Navigate to the publisher dashboard page
    window.location.href = `/publisher/${selectedPublisher}`;
  }
}

/**
 * Initialize the sidebar functionality
 */
function initializeSidebar() {
  // Load advertisers dropdown
  loadAdvertisers();
  // Load publishers dropdown
  loadPublishers();
  // Initialize service health indicators
  initializeServiceHealth();
}

/**
 * Initialize and start service health monitoring
 */
function initializeServiceHealth() {
  // Check if container exists
  const container = document.getElementById('service-health-indicators');
  if (!container) {
    console.error("Service health container not found!");
    return;
  }
  
  // Load initial service health
  loadServiceHealth();
  
  // Set up periodic refresh (every 30 seconds)
  setInterval(loadServiceHealth, 30000);
}

/**
 * Load and display service health indicators
 */
async function loadServiceHealth() {
  try {
    const response = await fetch("/api/services");
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    // Parse JSON response
    const data = await response.json();
    
    // Update the service health indicators
    updateServiceHealthDisplay(data.services || []);
    
  } catch (error) {
    console.error("Error loading service health:", error);
    // Show error in the health indicators container
    showServiceHealthError();
  }
}

/**
 * Update the service health indicators display
 * @param {Array} services - Array of service objects
 */
function updateServiceHealthDisplay(services) {
  const container = document.getElementById('service-health-indicators');
  
  if (!container) {
    console.warn('Service health indicators container not found');
    return;
  }
  
  // Clear existing indicators
  container.innerHTML = '';
  
  if (!services || services.length === 0) {
    container.innerHTML = '<div class="text-muted small">No services found</div>';
    return;
  }
  
  // Sort services alphabetically
  const sortedServices = services.sort((a, b) => a.name.localeCompare(b.name));
  
  // Filter and create health indicators - only show green (healthy) services
  const healthyServices = sortedServices.filter(service => {
    const healthStatus = calculateHealthStatus(service.last_updated);
    return healthStatus.status === 'green';
  });
  
  if (healthyServices.length === 0) {
    container.innerHTML = '<div class="text-muted small">No healthy services</div>';
    return;
  }
  
  // Create health indicators for healthy services only
  healthyServices.forEach(service => {
    const indicator = createServiceHealthIndicator(service);
    container.appendChild(indicator);
  });
}

/**
 * Create a health indicator for a service
 * @param {Object} service - Service object
 * @returns {HTMLElement} Health indicator element
 */
function createServiceHealthIndicator(service) {
  const indicator = document.createElement('div');
  indicator.className = 'service-health-indicator d-flex align-items-center mb-2';
  
  // Calculate health status
  const healthStatus = calculateHealthStatus(service.last_updated);
  
  // Create dot element
  const dot = document.createElement('span');
  dot.className = `service-health-dot rounded-circle me-2 ${healthStatus.class}`;
  dot.setAttribute('data-bs-toggle', 'tooltip');
  dot.setAttribute('data-bs-placement', 'right');
  dot.setAttribute('title', `${service.name}: ${healthStatus.tooltip}`);
  
  // Make dot clickable
  dot.style.cursor = 'pointer';
  dot.addEventListener('click', () => {
    navigateToService(service.name);
  });
  
  // Create service name label (optional, can be hidden with CSS)
  const label = document.createElement('span');
  label.className = 'service-health-label text-muted small';
  label.textContent = service.name;
  label.style.cursor = 'pointer';
  label.addEventListener('click', () => {
    navigateToService(service.name);
  });
  
  indicator.appendChild(dot);
  indicator.appendChild(label);
  
  // Initialize tooltip
  if (window.bootstrap && window.bootstrap.Tooltip) {
    new window.bootstrap.Tooltip(dot);
  }
  
  return indicator;
}

/**
 * Calculate health status based on last updated timestamp
 * @param {number} lastUpdated - Age in seconds since last update (not timestamp)
 * @returns {Object} Health status with class and tooltip
 */
function calculateHealthStatus(lastUpdated) {
  if (lastUpdated === null || lastUpdated === undefined) {
    return {
      class: 'service-health-red',
      tooltip: 'Never updated',
      status: 'red'
    };
  }
  
  // lastUpdated is already the age in seconds, not a timestamp
  const ageSeconds = lastUpdated;
  
  if (ageSeconds > 180) { // More than 3 minutes
    return {
      class: 'service-health-red',
      tooltip: `Last updated ${formatAge(ageSeconds)} ago - Service may be down`,
      status: 'red'
    };
  } else if (ageSeconds > 90) { // More than 90 seconds
    return {
      class: 'service-health-yellow',
      tooltip: `Last updated ${formatAge(ageSeconds)} ago - Service running slowly`,
      status: 'yellow'
    };
  } else {
    return {
      class: 'service-health-green',
      tooltip: `Last updated ${formatAge(ageSeconds)} ago - Service healthy`,
      status: 'green'
    };
  }
}

/**
 * Format age in human readable format
 * @param {number} seconds - Age in seconds
 * @returns {string} Formatted age string
 */
function formatAge(seconds) {
  if (seconds < 60) {
    return `${seconds} second${seconds !== 1 ? 's' : ''}`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
  } else {
    const hours = Math.floor(seconds / 3600);
    return `${hours} hour${hours !== 1 ? 's' : ''}`;
  }
}

/**
 * Navigate to service details page
 * @param {string} serviceName - Name of the service
 */
function navigateToService(serviceName) {
  // Navigate to services page with the specific service tab
  window.location.href = `/services#${serviceName}`;
}

/**
 * Show error message in service health container
 */
function showServiceHealthError() {
  const container = document.getElementById('service-health-indicators');
  
  if (container) {
    container.innerHTML = `
      <div class="text-danger small d-flex align-items-center">
        <i class="bi bi-exclamation-triangle me-2"></i>
        Error loading service status
      </div>
    `;
  }
}

// Auto-initialize if DOM is already loaded, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeSidebar);
} else {
  initializeSidebar();
}