// Services dashboard JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    console.log('Services dashboard loaded');
    
    // Initialize charts for all services
    if (window.servicesData && window.servicesData.length > 0) {
        initializeAllCharts();
    } else {
        console.warn('No services data available for chart initialization');
    }
    
    // Initialize URL-based tab navigation
    initializeTabNavigation();
    
    // Initialize settings form handlers
    initializeSettingsHandlers();
});

/**
 * Fetch service query metrics via API call for a specific service
 * The enhanced fetch wrapper will automatically track this as an XHR request
 * and inject the returned query_metrics into the query panel
 * @param {string} serviceName - Name of the service to fetch metrics for
 */
async function fetchServiceQueryMetrics(serviceName) {
    try {
        console.log(`Fetching query metrics for service: ${serviceName}`);
        
        // Clear existing queries from panel before fetching new ones
        // This is equivalent to clicking the trash can button
        if (typeof window.resetQueryCounters === 'function') {
            window.resetQueryCounters();
            console.log('Cleared existing query metrics from panel');
        } else {
            console.warn('resetQueryCounters function not available');
        }
        
        // This fetch call will be automatically intercepted by the enhanced fetch wrapper
        // in partial-query-system.js and the response query_metrics will be processed
        const response = await fetch(`/api/services/${serviceName}/query-metrics`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        console.log(`Service query metrics API call completed for ${serviceName}`);
        // The query_metrics in the response will be automatically processed by the 
        // enhanced fetch wrapper and added to the query panel
        
    } catch (error) {
        console.error(`Error fetching service query metrics for ${serviceName}:`, error);
        // The error will also be automatically tracked by the enhanced fetch wrapper
    }
}

/**
 * Initialize charts for all services
 */
function initializeAllCharts() {
    window.servicesData.forEach(service => {
        if (service.parsed_stats && Object.keys(service.parsed_stats).length > 0) {
            initializeServiceCharts(service);
        }
    });
}

/**
 * Initialize URL-based tab navigation
 */
function initializeTabNavigation() {
    console.log('Initializing URL-based tab navigation');
    
    // Handle tab switching events
    const tabLinks = document.querySelectorAll('#servicesTabs a[data-bs-toggle="tab"]');
    tabLinks.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(event) {
            const targetPane = event.target.getAttribute('data-bs-target');
            const serviceName = event.target.id.replace('-tab', '');
            const anchor = event.target.getAttribute('href');
            
            console.log(`Switched to service tab: ${serviceName}`);
            
            // Update URL with anchor (without triggering page reload)
            if (anchor && anchor !== window.location.hash) {
                history.replaceState(null, null, anchor);
            }
            
            // Refresh charts in the active tab to ensure proper rendering
            refreshChartsInPane(targetPane, serviceName);
            
            // Fetch query metrics for this specific service
            fetchServiceQueryMetrics(serviceName);
        });
    });
    
    // Handle browser back/forward navigation
    window.addEventListener('hashchange', function() {
        activateTabFromHash();
    });
    
    // Activate correct tab based on URL hash on page load
    activateTabFromHash();
}

/**
 * Activate the correct tab based on the current URL hash
 */
function activateTabFromHash() {
    const hash = window.location.hash;
    
    if (hash) {
        // Find the tab that matches the hash
        const tabLink = document.querySelector(`#servicesTabs a[href="${hash}"]`);
        
        if (tabLink) {
            console.log(`Activating tab from URL hash: ${hash}`);
            
            // Use Bootstrap's tab methods to switch to the correct tab
            const tab = new bootstrap.Tab(tabLink);
            tab.show();
            
            return; // Exit early since we found and activated the tab
        } else {
            console.warn(`No tab found for hash: ${hash}`);
        }
    }
    
    // If no hash or invalid hash, activate the first tab and set its hash
    const firstTabLink = document.querySelector('#servicesTabs a[data-bs-toggle="tab"]');
    if (firstTabLink) {
        console.log('No valid hash found, activating first tab');
        
        // Get the href from the first tab to use as default hash
        const defaultHash = firstTabLink.getAttribute('href');
        
        // Update URL with the default hash if there's no hash currently
        if (!window.location.hash && defaultHash) {
            history.replaceState(null, null, defaultHash);
        }
        
        // Activate the first tab
        const firstTab = new bootstrap.Tab(firstTabLink);
        firstTab.show();
    }
}

/**
 * Initialize charts for a specific service
 * @param {Object} service - Service data object
 */
function initializeServiceCharts(service) {
    console.log(`Initializing charts for service: ${service.name}`);
    
    Object.entries(service.parsed_stats).forEach(([metricName, metricData]) => {
        const chartId = `chart-${service.name}-${metricName}`;
        const canvas = document.getElementById(chartId);
        
        if (canvas) {
            createMetricChart(canvas, metricName, metricData);
            // Update the metric value display
            updateMetricValue(service.name, metricName, metricData);
        } else {
            console.warn(`Canvas not found for chart ID: ${chartId}`);
        }
    });
}

/**
 * Create a metric chart on the given canvas
 * @param {HTMLCanvasElement} canvas - Canvas element to render chart on
 * @param {string} metricName - Name of the metric
 * @param {Array} metricData - Array of [timestamp, value] pairs
 */
function createMetricChart(canvas, metricName, metricData) {
    const ctx = canvas.getContext('2d');
    
    // Process the data for Chart.js
    const chartData = processMetricData(metricData);
    
    // Determine chart type and configuration based on data
    const chartConfig = getChartConfiguration(metricName, chartData);
    
    // Create the chart
    try {
        const chart = new Chart(ctx, chartConfig);
        
        // Store chart instance for potential updates
        canvas.chartInstance = chart;
        
        console.log(`Created chart for metric: ${metricName}`);
    } catch (error) {
        console.error(`Failed to create chart for ${metricName}:`, error);
        
        // Show error message in canvas area
        showChartError(canvas, `Failed to render ${metricName} chart`);
    }
}

/**
 * Update metric value display
 * @param {string} serviceName - Name of the service
 * @param {string} metricName - Name of the metric
 * @param {Array} metricData - Array of [timestamp, value] pairs
 */
function updateMetricValue(serviceName, metricName, metricData) {
    const valueElementId = `value-${serviceName}-${metricName}`;
    const valueElement = document.getElementById(valueElementId);
    
    if (valueElement && metricData && metricData.length > 0) {
        // Get the latest value (last item in the sorted array)
        const sortedData = metricData.sort((a, b) => a[0] - b[0]);
        const latestValue = sortedData[sortedData.length - 1][1];
        
        // Format and display the value
        valueElement.textContent = formatValue(latestValue, metricName);
    }
}

/**
 * Process raw metric data into Chart.js format
 * @param {Array} rawData - Array of [timestamp, value] pairs
 * @returns {Object} Processed data with labels and values
 */
function processMetricData(rawData) {
    if (!Array.isArray(rawData) || rawData.length === 0) {
        return { labels: [], values: [] };
    }
    
    // Sort by timestamp
    const sortedData = rawData.sort((a, b) => a[0] - b[0]);
    
    const labels = [];
    const values = [];
    
    sortedData.forEach(([timestamp, value]) => {
        // Convert Unix timestamp to readable time with more detail
        const date = new Date(timestamp * 1000);
        const timeString = date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
        labels.push(timeString);
        values.push(parseFloat(value) || 0);
    });
    
    return { labels, values };
}

/**
 * Get chart configuration based on metric name and data
 * @param {string} metricName - Name of the metric
 * @param {Object} chartData - Processed chart data
 * @returns {Object} Chart.js configuration object
 */
function getChartConfiguration(metricName, chartData) {
    const config = {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: metricName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                data: chartData.values,
                borderColor: getMetricColor(metricName),
                backgroundColor: getMetricColor(metricName, 0.1),
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointBorderWidth: 0,
                pointHoverBorderWidth: 2,
                pointBackgroundColor: getMetricColor(metricName),
                pointHoverBackgroundColor: getMetricColor(metricName),
                pointBorderColor: '#fff',
                pointHoverBorderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    display: false,
                    beginAtZero: false
                },
                x: {
                    display: false
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: getMetricColor(metricName),
                    borderWidth: 1,
                    displayColors: false,
                    cornerRadius: 6,
                    caretPadding: 8,
                    titleFont: {
                        size: 12,
                        weight: 'bold'
                    },
                    bodyFont: {
                        size: 11
                    },
                    callbacks: {
                        title: function(tooltipItems) {
                            // Show the time
                            return tooltipItems[0].label;
                        },
                        label: function(context) {
                            const value = context.parsed.y;
                            return `${formatValue(value, metricName)}`;
                        }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            onHover: (event, elements) => {
                event.native.target.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            },
            elements: {
                point: {
                    radius: 0,
                    hoverRadius: 4
                }
            }
        }
    };
    
    return config;
}

/**
 * Get color for a metric based on its name
 * @param {string} metricName - Name of the metric
 * @param {number} alpha - Alpha value for transparency (optional)
 * @returns {string} Color string
 */
function getMetricColor(metricName, alpha = 1) {
    const colorMap = {
        'cpu': '#dc3545',
        'memory': '#28a745',
        'disk': '#ffc107',
        'network': '#007bff',
        'requests': '#6610f2',
        'errors': '#fd7e14',
        'latency': '#20c997',
        'throughput': '#6f42c1'
    };
    
    // Find matching color based on metric name keywords
    for (const [keyword, color] of Object.entries(colorMap)) {
        if (metricName.toLowerCase().includes(keyword)) {
            return alpha < 1 ? `${color}${Math.round(alpha * 255).toString(16).padStart(2, '0')}` : color;
        }
    }
    
    // Default color with alpha
    const defaultColor = '#6c757d';
    return alpha < 1 ? `${defaultColor}${Math.round(alpha * 255).toString(16).padStart(2, '0')}` : defaultColor;
}

/**
 * Format value for display based on metric type
 * @param {number} value - Numeric value
 * @param {string} metricName - Name of the metric
 * @returns {string} Formatted value
 */
function formatValue(value, metricName) {
    if (metricName.includes('percent') || metricName.includes('rate')) {
        return `${value.toFixed(2)}%`;
    } else if (metricName.includes('bytes') || metricName.includes('memory')) {
        return formatBytes(value);
    } else if (metricName.includes('seconds')) {
        return `${value.toFixed(3)}s`;
    } else if (metricName.includes('time') || metricName.includes('latency')) {
        return `${value.toFixed(2)}ms`;
    } else {
        return value.toLocaleString();
    }
}

/**
 * Format bytes into human readable format
 * @param {number} bytes - Number of bytes
 * @returns {string} Formatted string
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Refresh charts in a specific tab pane
 * @param {string} targetPane - CSS selector for target pane
 * @param {string} serviceName - Name of the service
 */
function refreshChartsInPane(targetPane, serviceName) {
    const pane = document.querySelector(targetPane);
    if (!pane) return;
    
    const canvases = pane.querySelectorAll('canvas[id^="chart-"]');
    canvases.forEach(canvas => {
        if (canvas.chartInstance) {
            // Update chart to ensure proper rendering after tab switch
            setTimeout(() => {
                canvas.chartInstance.resize();
                canvas.chartInstance.update('none');
            }, 100);
        }
    });
}

/**
 * Show error message in place of chart
 * @param {HTMLCanvasElement} canvas - Canvas element
 * @param {string} message - Error message
 */
function showChartError(canvas, message) {
    const ctx = canvas.getContext('2d');
    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    
    canvas.width = width;
    canvas.height = height;
    
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, width, height);
    
    ctx.fillStyle = '#6c757d';
    ctx.font = '14px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(message, width / 2, height / 2);
}

/**
 * Utility function to handle Chart.js registration errors
 */
function handleChartJSError(error) {
    console.error('Chart.js error:', error);
    
    // Show error message to user
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-warning mt-3';
    alertDiv.innerHTML = `
        <i class="bi bi-exclamation-triangle"></i>
        Charts could not be loaded. Please refresh the page or check your connection.
    `;
    
    const mainContent = document.querySelector('.col-md-9 .p-3');
    if (mainContent) {
        mainContent.insertBefore(alertDiv, mainContent.firstChild);
    }
}

// Global error handling for Chart.js
window.addEventListener('error', function(event) {
    if (event.message && event.message.includes('Chart')) {
        handleChartJSError(event.error);
    }
});

/**
 * Initialize settings form handlers for all services
 */
function initializeSettingsHandlers() {
    console.log('Initializing settings form handlers');
    
    // Find all save buttons and forms, attach handlers
    const saveButtons = document.querySelectorAll('[id^="save-settings-"]');
    saveButtons.forEach(button => {
        const serviceName = button.id.replace('save-settings-', '');
        const form = document.getElementById(`settings-form-${serviceName}`);
        
        if (form) {
            // Store original values for change detection
            storeOriginalValues(serviceName, form);
            
            // Add input change listeners to all form inputs
            const inputs = form.querySelectorAll('input');
            inputs.forEach(input => {
                input.addEventListener('input', () => checkForChanges(serviceName));
                input.addEventListener('change', () => checkForChanges(serviceName));
            });
        }
        
        // Save button handler
        button.addEventListener('click', () => saveSettings(serviceName));
    });
}

/**
 * Store original form values for change detection
 * @param {string} serviceName - Name of the service
 * @param {HTMLFormElement} form - The form element
 */
function storeOriginalValues(serviceName, form) {
    const originalValues = {};
    const inputs = form.querySelectorAll('input');
    
    inputs.forEach(input => {
        originalValues[input.name] = input.value;
    });
    
    // Store in a global object for later comparison
    if (!window.originalFormValues) {
        window.originalFormValues = {};
    }
    window.originalFormValues[serviceName] = originalValues;
}

/**
 * Check for changes in form values and update save button state
 * @param {string} serviceName - Name of the service
 */
function checkForChanges(serviceName) {
    const form = document.getElementById(`settings-form-${serviceName}`);
    const saveBtn = document.getElementById(`save-settings-${serviceName}`);
    
    if (!form || !saveBtn || !window.originalFormValues || !window.originalFormValues[serviceName]) {
        return;
    }
    
    const originalValues = window.originalFormValues[serviceName];
    const inputs = form.querySelectorAll('input');
    let hasChanges = false;
    
    inputs.forEach(input => {
        if (input.value !== originalValues[input.name]) {
            hasChanges = true;
        }
    });
    
    // Enable/disable save button based on changes
    saveBtn.disabled = !hasChanges;
    
    // Update button appearance
    if (hasChanges) {
        saveBtn.classList.remove('btn-outline-primary');
        saveBtn.classList.add('btn-primary');
        saveBtn.title = 'Click to save changes';
    } else {
        saveBtn.classList.remove('btn-primary');
        saveBtn.classList.add('btn-outline-primary');
        saveBtn.title = 'No changes to save';
    }
}

/**
 * Save settings changes
 * @param {string} serviceName - Name of the service
 */
async function saveSettings(serviceName) {
    console.log(`Saving settings for service: ${serviceName}`);
    
    const form = document.getElementById(`settings-form-${serviceName}`);
    const saveBtn = document.getElementById(`save-settings-${serviceName}`);
    
    if (!form) {
        console.error('Settings form not found');
        return;
    }
    
    // Collect form data
    const formData = new FormData(form);
    const settings = {};
    
    for (let [key, value] of formData.entries()) {
        // Convert numeric values
        if (value.match(/^\d+$/)) {
            settings[key] = parseInt(value);
        } else {
            settings[key] = value;
        }
    }
    
    console.log('Settings to save:', settings);
    
    try {
        // Disable save button and show saving state
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
            saveBtn.classList.remove('btn-primary', 'btn-outline-primary');
            saveBtn.classList.add('btn-warning');
        }
        
        // Send PUT request to update settings
        const response = await fetch(`/api/services/${serviceName}/settings`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('Settings saved successfully:', result);
            
            // Update original values to new saved values
            storeOriginalValues(serviceName, form);
            
            // Show success state briefly
            if (saveBtn) {
                saveBtn.innerHTML = '<i class="bi bi-check-circle"></i> Saved!';
                saveBtn.classList.remove('btn-warning');
                saveBtn.classList.add('btn-success');
            }
            
            // Show success notification
            showNotification(`Configuration saved successfully for ${serviceName}!`, 'success');
            
            // After a brief delay, reset button to disabled state
            setTimeout(() => {
                if (saveBtn) {
                    saveBtn.innerHTML = '<i class="bi bi-check"></i> Save';
                    saveBtn.disabled = true;
                    saveBtn.classList.remove('btn-success');
                    saveBtn.classList.add('btn-outline-primary');
                    saveBtn.title = 'No changes to save';
                }
            }, 2000);
            
        } else {
            const errorData = await response.json();
            console.error('Failed to save settings:', errorData);
            showNotification(`Failed to save settings: ${errorData.detail || 'Unknown error'}`, 'danger');
            
            // Reset button to error state, then back to normal
            if (saveBtn) {
                saveBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Error';
                saveBtn.classList.remove('btn-warning');
                saveBtn.classList.add('btn-danger');
                
                setTimeout(() => {
                    saveBtn.innerHTML = '<i class="bi bi-check"></i> Save';
                    saveBtn.classList.remove('btn-danger');
                    saveBtn.classList.add('btn-primary');
                    // Re-check for changes to set proper state
                    checkForChanges(serviceName);
                }, 3000);
            }
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showNotification('Error saving settings. Please check your connection and try again.', 'danger');
        
        // Reset button to error state, then back to normal
        if (saveBtn) {
            saveBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Error';
            saveBtn.classList.remove('btn-warning');
            saveBtn.classList.add('btn-danger');
            
            setTimeout(() => {
                saveBtn.innerHTML = '<i class="bi bi-check"></i> Save';
                saveBtn.classList.remove('btn-danger');
                saveBtn.classList.add('btn-primary');
                // Re-check for changes to set proper state
                checkForChanges(serviceName);
            }, 3000);
        }
    }
}

/**
 * Show notification message
 * @param {string} message - Message to show
 * @param {string} type - Bootstrap alert type (success, danger, warning, info)
 */
function showNotification(message, type = 'info') {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.settings-notification');
    existingNotifications.forEach(notification => notification.remove());
    
    // Create new notification with enhanced styling
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show settings-notification mt-3`;
    
    // Add appropriate icon based on type
    let icon = 'bi-info-circle';
    if (type === 'success') icon = 'bi-check-circle-fill';
    else if (type === 'danger') icon = 'bi-exclamation-triangle-fill';
    else if (type === 'warning') icon = 'bi-exclamation-circle-fill';
    
    notification.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="bi ${icon} me-2"></i>
            <span>${message}</span>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Insert notification at top of main content
    const mainContent = document.querySelector('.col-md-9 .p-3');
    if (mainContent) {
        mainContent.insertBefore(notification, mainContent.firstChild);
        
        // Auto-remove after 5 seconds for success, 8 seconds for errors
        const autoRemoveTime = type === 'success' ? 5000 : 8000;
        setTimeout(() => {
            if (notification && notification.parentElement) {
                notification.classList.remove('show');
                setTimeout(() => {
                    if (notification.parentElement) {
                        notification.remove();
                    }
                }, 150); // Allow fade out animation
            }
        }, autoRemoveTime);
    }
    
    // Also show a toast-style notification for success
    if (type === 'success') {
        showToastNotification(message, 'success');
    }
}

/**
 * Show a toast-style notification in the top-right corner
 * @param {string} message - Message to show
 * @param {string} type - Notification type
 */
function showToastNotification(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '1055';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="bi bi-check-circle-fill me-2"></i>${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Initialize and show the toast using Bootstrap
    if (window.bootstrap && window.bootstrap.Toast) {
        const bootstrapToast = new window.bootstrap.Toast(toast, {
            autohide: true,
            delay: 4000
        });
        bootstrapToast.show();
        
        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    } else {
        // Fallback if Bootstrap Toast is not available
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentElement) {
                    toast.remove();
                }
            }, 150);
        }, 4000);
    }
}