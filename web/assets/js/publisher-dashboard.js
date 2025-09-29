/**
 * Publisher Dashboard JavaScript
 * Handles dashboard data loading, chart rendering, and publisher-specific functionality
 */

/**
 * Get current publisher ID from the page data attribute
 */
function getCurrentPublisherId() {
  const body = document.body;
  return body.getAttribute('data-publisher-id');
}

/**
 * Load publisher dashboard data
 */
async function loadDashboardData() {
  const publisherId = getCurrentPublisherId();
  
  if (!publisherId) {
    console.error("No publisher ID found in URL");
    showError("Invalid publisher ID");
    return;
  }
  
  try {
    const response = await fetch(`/api/publishers/${publisherId}/dashboard`);
    const data = await response.json();
    
    if (response.ok && data.dashboard) {
      const dashboard = data.dashboard;
      
      // Update dashboard content
      updateElement("publisher-name", dashboard.name);
      updateElement("publisher-id", dashboard.publisher_id);
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
      
    } else {
      throw new Error(data.error || "Failed to load dashboard data");
    }
    
  } catch (error) {
    console.error("Error loading dashboard data:", error);
    showError(error.message || "Failed to load publisher data.");
  }
}

/**
 * Load and render chart data
 */
async function loadChartData() {
  const publisherId = getCurrentPublisherId();
  
  if (!publisherId) {
    console.error("No publisher ID found for chart loading");
    return;
  }
  
  try {
    const response = await fetch(`/api/publishers/${publisherId}/chart`);
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
 * Initialize the publisher dashboard page
 */
function initializePublisherDashboard() {
  loadDashboardData();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializePublisherDashboard);
} else {
  initializePublisherDashboard();
}