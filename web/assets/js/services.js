// Services dashboard JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    console.log('Services dashboard loaded');
    
    // Initialize charts for all services
    if (window.servicesData && window.servicesData.length > 0) {
        initializeAllCharts();
    } else {
        console.warn('No services data available for chart initialization');
    }
    
    // Handle tab switching
    const tabLinks = document.querySelectorAll('#servicesTabs button[data-bs-toggle="tab"]');
    tabLinks.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(event) {
            const targetPane = event.target.getAttribute('data-bs-target');
            const serviceName = event.target.id.replace('-tab', '');
            console.log(`Switched to service tab: ${serviceName}`);
            
            // Refresh charts in the active tab to ensure proper rendering
            refreshChartsInPane(targetPane, serviceName);
        });
    });
});

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