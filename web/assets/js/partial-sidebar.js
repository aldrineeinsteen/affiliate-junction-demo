/**
 * Sidebar Partial JavaScript
 * Handles the advertiser dropdown functionality for sidebar.html partial
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
 * Handle advertiser selection change
 */
function onAdvertiserChange() {
  const select = document.getElementById("advertisersSelect");
  if (!select) return;
  
  const selectedAdvertiser = select.value;
  
  if (selectedAdvertiser) {
    console.log("Selected advertiser:", selectedAdvertiser);
    // Navigate to the advertiser dashboard page
    window.location.href = `/advertiser/${selectedAdvertiser}`;
  }
}

/**
 * Initialize the sidebar functionality
 */
function initializeSidebar() {
  // Load advertisers dropdown
  loadAdvertisers();
}

// Auto-initialize if DOM is already loaded, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeSidebar);
} else {
  initializeSidebar();
}