/**
 * Advertiser Dashboard JavaScript
 * Handles dashboard data loading, chart rendering, and advertiser-specific functionality
 */

/**
 * Get current advertiser ID from the page data attribute
 */
function getCurrentAdvertiserId() {
  const body = document.body;
  return body.getAttribute('data-advertiser-id');
}

/**
 * Load advertiser dashboard data
 */
async function loadDashboardData() {
  const advertiserId = getCurrentAdvertiserId();
  
  if (!advertiserId) {
    console.error("No advertiser ID found in URL");
    showError("Invalid advertiser ID");
    return;
  }
  
  try {
    const response = await fetch(`/api/advertisers/${advertiserId}/dashboard`);
    const data = await response.json();
    
    if (response.ok && data.dashboard) {
      const dashboard = data.dashboard;
      
      // Update dashboard content
      updateElement("advertiser-name", dashboard.name);
      updateElement("advertiser-id", dashboard.advertiser_id);
      updateElement("total-impressions", dashboard.total_impressions.toLocaleString());
      updateElement("total-conversions", dashboard.total_conversions.toLocaleString());
      
      // Calculate conversion rate
      const conversionRate = dashboard.total_impressions > 0 
        ? ((dashboard.total_conversions / dashboard.total_impressions) * 100).toFixed(2)
        : "0.00";
      updateElement("conversion-rate", `${conversionRate}%`);
      
      // Format last updated time
      if (dashboard.last_updated) {
        const lastUpdated = new Date(dashboard.last_updated).toLocaleString();
        updateElement("last-updated", lastUpdated);
      }
      
      // Show dashboard content
      hideElement("loading");
      showElement("dashboard");
      
      // Load chart data after dashboard is loaded
      loadChartData();
      
      // Load conversions data after dashboard is loaded
      loadConversionsData();
      
    } else {
      throw new Error(data.error || "Failed to load dashboard data");
    }
    
  } catch (error) {
    console.error("Error loading dashboard data:", error);
    showError(error.message || "Failed to load advertiser data.");
  }
}

/**
 * Load and render chart data
 */
async function loadChartData() {
  const advertiserId = getCurrentAdvertiserId();
  
  if (!advertiserId) {
    console.error("No advertiser ID found for chart loading");
    return;
  }
  
  try {
    const response = await fetch(`/api/advertisers/${advertiserId}/chart`);
    const data = await response.json();
    
    if (response.ok && data.chart) {
      renderTimeSeriesChart(data.chart);
    } else {
      throw new Error(data.error || "Failed to load chart data");
    }
    
  } catch (error) {
    console.error("Error loading chart data:", error);
    showChartError();
  }
}

/**
 * Render the time series chart using Chart.js
 */
function renderTimeSeriesChart(chartData) {
  const canvas = document.getElementById('timeSeriesChart');
  if (!canvas) {
    console.error('Time series chart canvas not found');
    return;
  }
  
  const ctx = canvas.getContext('2d');
  
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: chartData.labels,
      datasets: [
        {
          label: 'Impressions',
          data: chartData.impressions,
          borderColor: '#0d6efd',        // Bootstrap primary blue
          backgroundColor: 'rgba(13, 110, 253, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4
        },
        {
          label: 'Conversions',
          data: chartData.conversions,
          borderColor: '#198754',        // Bootstrap success green
          backgroundColor: 'rgba(25, 135, 84, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        title: {
          display: true,
          text: 'Impressions vs Conversions Over Time',
          font: {
            size: 16
          }
        },
        legend: {
          position: 'top',
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          titleColor: '#fff',
          bodyColor: '#fff',
          borderColor: '#dee2e6',
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: true
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Time',
            font: {
              size: 12
            }
          },
          grid: {
            display: true,
            color: 'rgba(0, 0, 0, 0.1)'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Count',
            font: {
              size: 12
            }
          },
          beginAtZero: true,
          grid: {
            display: true,
            color: 'rgba(0, 0, 0, 0.1)'
          }
        }
      }
    }
  });

  // Hide loading state and show chart
  hideElement("chart-loading");
  showElement("chart-container");
  
  // Set chart container height for better visualization
  const chartContainer = document.getElementById("chart-container");
  if (chartContainer) {
    chartContainer.style.height = "400px";
  }
  
  // Render sparkline charts with the same data
  renderSparklineCharts(chartData);
}

/**
 * Render sparkline charts
 */
function renderSparklineCharts(chartData) {
  // Render impressions sparkline
  renderSparkline('impressionsSparkline', chartData.impressions, '#0d6efd');
  
  // Render conversions sparkline
  renderSparkline('conversionsSparkline', chartData.conversions, '#198754');
}

/**
 * Generic sparkline renderer
 */
function renderSparkline(canvasId, data, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    console.warn(`Sparkline canvas ${canvasId} not found`);
    return;
  }
  
  const ctx = canvas.getContext('2d');
  
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map((_, index) => index), // Simple index labels
      datasets: [{
        data: data,
        borderColor: color,
        backgroundColor: color + '20', // Add transparency
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0, // Hide points for cleaner look
        pointHoverRadius: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          display: false
        },
        y: {
          display: false,
          beginAtZero: true
        }
      },
      elements: {
        line: {
          borderJoinStyle: 'round'
        }
      },
      interaction: {
        intersect: false,
        mode: 'index'
      }
    }
  });
}

/**
 * Load and display conversions data
 */
async function loadConversionsData() {
  const advertiserId = getCurrentAdvertiserId();
  
  if (!advertiserId) {
    console.error("No advertiser ID found for conversions loading");
    return;
  }
  
  try {
    const response = await fetch(`/api/advertisers/${advertiserId}/conversions`);
    const data = await response.json();
    
    if (response.ok) {
      renderConversionsAccordion(data.conversions);
    } else {
      throw new Error(data.error || "Failed to load conversions data");
    }
    
  } catch (error) {
    console.error("Error loading conversions data:", error);
    showConversionsError();
  }
}

/**
 * Render the conversions accordion
 */
function renderConversionsAccordion(conversions) {
  const accordionContainer = document.getElementById('conversionsAccordion');
  
  if (!accordionContainer) {
    console.error('Conversions accordion container not found');
    return;
  }
  
  // Clear existing content
  accordionContainer.innerHTML = '';
  
  if (!conversions || conversions.length === 0) {
    hideElement("conversions-loading");
    showElement("no-conversions");
    return;
  }
  
  // Add conversions-accordion class to the accordion
  accordionContainer.className = 'accordion conversions-accordion';
  
  // Create accordion items for each conversion
  conversions.forEach((conversion, index) => {
    const accordionItem = createConversionAccordionItem(conversion, index);
    accordionContainer.appendChild(accordionItem);
  });
  
  // Hide loading state and show conversions
  hideElement("conversions-loading");
  showElement("conversions-container");
}

/**
 * Create an accordion item for a single conversion
 */
function createConversionAccordionItem(conversion, index) {
  const itemId = `conversion-${index}`;
  const headingId = `heading-${index}`;
  const collapseId = `collapse-${index}`;
  
  // Format timestamps
  const conversionTime = new Date(conversion.conversion_timestamp || conversion.timestamp).toLocaleString();
  const impressionTime = conversion.impression_timestamp ? new Date(conversion.impression_timestamp).toLocaleString() : 'N/A';
  
  // Calculate time to conversion in a readable format
  let timeToConversion = 'N/A';
  if (conversion.time_to_conversion_seconds) {
    const seconds = conversion.time_to_conversion_seconds;
    if (seconds < 60) {
      timeToConversion = `${seconds}s`;
    } else if (seconds < 3600) {
      timeToConversion = `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      timeToConversion = `${hours}h ${minutes}m`;
    }
  }
  
  // Create the accordion item
  const accordionItem = document.createElement('div');
  accordionItem.className = 'accordion-item';
  
  accordionItem.innerHTML = `
    <h2 class="accordion-header" id="${headingId}">
      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" 
              data-bs-target="#${collapseId}" aria-expanded="false" 
              aria-controls="${collapseId}"
              data-cookie-id="${conversion.cookie_id}">
        <div class="conversion-header">
          <span class="conversion-cookie">Cookie: ${conversion.cookie_id}</span>
          <span class="conversion-timestamp">${conversionTime}</span>
        </div>
      </button>
    </h2>
    <div id="${collapseId}" class="accordion-collapse collapse" 
         aria-labelledby="${headingId}" data-bs-parent="#conversionsAccordion">
      <div class="accordion-body">
        <div class="row">
          <div class="col-md-6">
            <h6>📊 Conversion Details</h6>
            <table class="table table-sm">
              <tbody>
                <tr>
                  <td><strong>Cookie ID:</strong></td>
                  <td><code>${conversion.cookie_id}</code></td>
                </tr>
                <tr>
                  <td><strong>Publisher:</strong></td>
                  <td>${conversion.publisher_id || 'N/A'}</td>
                </tr>
                <tr>
                  <td><strong>Time to Convert:</strong></td>
                  <td>${timeToConversion}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="col-md-6">
            <h6>⏱️ Timeline</h6>
            <table class="table table-sm">
              <tbody>
                <tr>
                  <td><strong>Impression:</strong></td>
                  <td>${impressionTime}</td>
                </tr>
                <tr>
                  <td><strong>Conversion:</strong></td>
                  <td>${conversionTime}</td>
                </tr>
                <tr>
                  <td><strong>Created:</strong></td>
                  <td>${conversion.created_at ? new Date(conversion.created_at).toLocaleString() : 'N/A'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="mt-3">
          <div class="alert alert-info">
            <small>
              <strong>🔗 Attribution Flow:</strong> 
              User saw impression from <strong>${conversion.publisher_id || 'Unknown Publisher'}</strong> 
              and converted ${timeToConversion} later.
            </small>
          </div>
        </div>
        
        <!-- Timeline Container (will be populated when expanded) -->
        <div id="timeline-${conversion.cookie_id}" class="timeline-placeholder"></div>
      </div>
    </div>
  `;
  
  // Add event listener for accordion expansion
  const collapseElement = accordionItem.querySelector(`#${collapseId}`);
  collapseElement.addEventListener('show.bs.collapse', function() {
    loadConversionTimeline(conversion.cookie_id);
  });
  
  return accordionItem;
}

/**
 * Load and display timeline for a specific conversion
 */
async function loadConversionTimeline(cookieId) {
  const advertiserId = getCurrentAdvertiserId();
  const timelineContainer = document.getElementById(`timeline-${cookieId}`);
  
  if (!timelineContainer || !advertiserId) {
    console.error("Timeline container or advertiser ID not found");
    return;
  }
  
  // Show loading state with progress bar
  timelineContainer.innerHTML = `
    <div class="timeline-loading">
      <div class="timeline-loading-text">Presto query to load timeline...</div>
      <div class="progress" style="height: 12px; margin-top: 10px; background-color: #e9ecef;">
        <div class="progress-bar progress-bar-striped progress-bar-animated" 
             role="progressbar" 
             style="width: 0%; transition: none; background-color: #0d6efd;"
             aria-valuenow="0" 
             aria-valuemin="0" 
             aria-valuemax="100">
        </div>
      </div>
      <div class="progress-percentage" style="font-size: 0.75rem; color: #6c757d; margin-top: 5px;">0%</div>
    </div>
  `;
  
  let progressComplete = false;
  let apiComplete = false;
  let apiData = null;
  let apiError = null;
  
  // Start the 30-second progress bar with even increments
  const progressBar = timelineContainer.querySelector('.progress-bar');
  const progressText = timelineContainer.querySelector('.progress-percentage');
  let currentProgress = 0;
  
  const progressInterval = setInterval(() => {
    if (progressComplete) {
      clearInterval(progressInterval);
      return;
    }
    
    currentProgress += (100 / 600); // 600 increments over 30 seconds
    
    if (currentProgress >= 100) {
      currentProgress = 100;
      progressComplete = true;
      clearInterval(progressInterval);
    }
    
    if (progressBar) {
      progressBar.style.width = `${currentProgress}%`;
      progressBar.setAttribute('aria-valuenow', Math.round(currentProgress));
    }
    if (progressText) {
      progressText.textContent = `${Math.round(currentProgress)}%`;
    }
    
    // If API completed early, finish the progress and show results
    if (apiComplete) {
      progressComplete = true;
      clearInterval(progressInterval);
      
      if (progressBar) {
        progressBar.style.width = '100%';
        progressBar.setAttribute('aria-valuenow', '100');
      }
      if (progressText) {
        progressText.textContent = '100%';
      }
      
      // Small delay to show 100% completion, then render results
      setTimeout(() => {
        if (apiError) {
          showTimelineError(timelineContainer, apiError);
        } else if (apiData) {
          renderConversionTimeline(timelineContainer, apiData);
        }
      }, 500);
    }
  }, 100); // Update every 100ms for smooth animation
  
  try {
    const response = await fetch(`/api/advertisers/${advertiserId}/conversions/${cookieId}/timeline`);
    const data = await response.json();
    
    if (response.ok && data.timeline) {
      apiData = data;
      apiComplete = true;
      
      // If progress bar already finished, show results immediately
      if (progressComplete) {
        renderConversionTimeline(timelineContainer, data);
      }
    } else {
      apiError = data.error || "Failed to load timeline data";
      apiComplete = true;
      
      // If progress bar already finished, show error immediately
      if (progressComplete) {
        showTimelineError(timelineContainer, apiError);
      }
    }
    
  } catch (error) {
    console.error(`Error loading timeline for cookie ${cookieId}:`, error);
    apiError = error.message;
    apiComplete = true;
    
    // If progress bar already finished, show error immediately
    if (progressComplete) {
      showTimelineError(timelineContainer, apiError);
    }
  }
}

/**
 * Render the conversion timeline
 */
function renderConversionTimeline(container, timelineData) {
  const { timeline, total_impressions, unique_publishers, first_impression, conversion_time } = timelineData;
  
  if (!timeline || timeline.length === 0) {
    container.innerHTML = `
      <div class="timeline-empty">
        <div class="timeline-empty-icon">📊</div>
        <div class="timeline-empty-text">No impression timeline data available for this conversion.</div>
      </div>
    `;
    return;
  }
  
  // Create timeline HTML
  let timelineHTML = `
    <div class="conversion-timeline">
      <div class="timeline-header">
        <h6 class="timeline-title">🔗 Impression Timeline</h6>
        <div class="timeline-summary">
          ${total_impressions} impressions • ${unique_publishers} publishers
        </div>
      </div>
      <div class="timeline-container">
  `;
  
  // Sort timeline by timestamp
  const sortedTimeline = timeline.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  
  // Add timeline items
  sortedTimeline.forEach((item, index) => {
    const isFirst = index === 0;
    const isLast = index === sortedTimeline.length - 1;
    
    let itemClass = 'timeline-item';
    if (isFirst) itemClass += ' first-impression';
    if (isLast) itemClass += ' conversion-event';
    
    timelineHTML += `
      <div class="${itemClass}">
        <div class="timeline-content">
          <div class="timeline-time">${item.formatted_time}</div>
          <div class="timeline-publisher">
            Publisher: <strong>${item.publisher_id}</strong>
          </div>
          <div class="timeline-impressions">
            <span class="badge bg-primary">${item.impressions} impression${item.impressions !== 1 ? 's' : ''}</span>
            ${isFirst ? '<span class="badge bg-warning ms-1">First</span>' : ''}
            ${isLast ? '<span class="badge bg-success ms-1">Conversion</span>' : ''}
          </div>
        </div>
      </div>
    `;
  });
  
  timelineHTML += `
      </div>
    </div>
  `;
  
  container.innerHTML = timelineHTML;
}

/**
 * Show timeline error state
 */
function showTimelineError(container, errorMessage) {
  container.innerHTML = `
    <div class="timeline-error">
      <div class="timeline-error-icon">⚠️</div>
      <div class="timeline-error-text">
        Failed to load timeline: ${errorMessage}
      </div>
    </div>
  `;
}

/**
 * Show conversions error state
 */
function showConversionsError() {
  hideElement("conversions-loading");
  const conversionsErrorEl = document.getElementById("conversions-error");
  if (conversionsErrorEl) {
    conversionsErrorEl.classList.remove("d-none");
  }
}

// Utility functions
function updateElement(id, content) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = content;
  }
}

function hideElement(id) {
  const element = document.getElementById(id);
  if (element) {
    element.style.display = "none";
  }
}

function showElement(id) {
  const element = document.getElementById(id);
  if (element) {
    element.classList.remove("d-none");
  }
}

function showError(message) {
  hideElement("loading");
  const errorEl = document.getElementById("error");
  const errorMessageEl = document.getElementById("error-message");
  
  if (errorEl && errorMessageEl) {
    errorMessageEl.textContent = message;
    errorEl.classList.remove("d-none");
  }
}

function showChartError() {
  hideElement("chart-loading");
  const chartErrorEl = document.getElementById("chart-error");
  if (chartErrorEl) {
    chartErrorEl.classList.remove("d-none");
  }
}

/**
 * Initialize the advertiser dashboard page
 */
function initializeAdvertiserDashboard() {
  loadDashboardData();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeAdvertiserDashboard);
} else {
  initializeAdvertiserDashboard();
}