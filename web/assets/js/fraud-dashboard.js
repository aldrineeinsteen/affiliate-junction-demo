/**
 * Fraud Dashboard JavaScript
 * Handl      // Convert stage 1 data to basic fraud data format and render immediately
      const basicFraudData = convertStage1ToFraudData(stage1Data.stage1_data);
      renderInitialFraudData(basicFraudData, stage1Data);
      
      updateProgress(35, "Stage 2: Analyzing publisher patterns (optimized query)...");detection data loading, table rendering, and progress bar functionality
 */

/**
 * Global state for fraud data
 */
let fraudData = [];
let filteredData = [];
let currentRiskFilter = '';
let currentSearchTerm = '';

/**
 * Load fraud detection data with two-stage progress bar
 */
async function loadFraudData() {
  showLoadingState();
  
  let stage1Complete = false;
  let stage2Complete = false;
  let stage1Data = null;
  let stage2Data = null;
  let currentError = null;
  
  // Progress bar elements
  const progressBar = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-percentage');
  let currentProgress = 0;
  
  // Stage 1: Load initial high-conversion cookies (30% of progress)
  try {
    updateProgress(5, "Stage 1: Identifying high-conversion cookies...");
    
    const stage1Response = await fetch('/api/fraud/stage1');
    const stage1Result = await stage1Response.json();
    
    if (stage1Response.ok && stage1Result.stage1_data) {
      stage1Data = stage1Result;
      stage1Complete = true;
      updateProgress(30, "Stage 1 complete - Drawing initial table...");
      
      // Convert stage 1 data to basic fraud data format and render immediately
      const basicFraudData = convertStage1ToFraudData(stage1Data.stage1_data);
      renderInitialFraudData(basicFraudData, stage1Data);
      
      // Show dashboard immediately with stage 1 data
      hideElement('loading');
      showElement('dashboard');
      
      updateProgress(35, "Stage 2: Analyzing publisher patterns (90min window)...");
      
    } else {
      throw new Error(stage1Result.error || "Failed to load stage 1 fraud data");
    }
    
  } catch (error) {
    console.error("Error in stage 1:", error);
    currentError = `Stage 1 error: ${error.message}`;
    showError(currentError);
    return;
  }
  
  // Stage 2: Enhanced analysis with optimized query using Stage 1 cookie_ids
  try {
    // Extract cookie_ids from stage 1 for targeted stage 2 query
    const cookieIds = stage1Data.stage1_data.map(item => item.cookie_id);
    
    updateProgress(35, "Stage 2: Analyzing publisher patterns (optimized query)...");
    
    // Start progress simulation for 75-second query
    let stage2Progress = 35;
    let stage2Complete = false;
    let stage2Result = null;
    let stage2Error = null;
    let progressInterval = null;
    
    // Progress increment every 2 seconds over 75 seconds (from 35% to 90%)
    const progressIncrement = (90 - 35) / (75 / 2); // 55% over 37.5 intervals
    progressInterval = setInterval(() => {
      if (stage2Complete) {
        clearInterval(progressInterval);
        
        updateProgress(90, "Stage 2 complete - Enhancing table with publisher data...");
        
        // Brief pause before enhancing the table
        setTimeout(() => {
          updateProgress(100, "Analysis complete - Enhanced view ready");
          
          if (stage2Error) {
            updateProgress(100, "Stage 1 complete - Stage 2 enhancement failed");
            console.warn("Stage 2 enhancement failed, showing Stage 1 data only:", stage2Error);
          } else if (stage2Result) {
            // Enhance the existing table with stage 2 data
            enhanceFraudDataWithStage2(stage2Result);
          }
          
          // Hide the progress bar after completion
          setTimeout(() => {
            hideProgressBar();
          }, 2000);
        }, 500);
        return;
      }
      
      stage2Progress += progressIncrement;
      
      if (stage2Progress >= 90) {
        stage2Progress = 90;
      }
      
      // Update progress message based on completion percentage
      let message = "Stage 2: Analyzing publisher patterns (optimized query)...";
      if (stage2Progress >= 45) {
        message = "Stage 2: Processing 90-minute publisher window...";
      }
      if (stage2Progress >= 60) {
        message = "Stage 2: Aggregating publisher diversity metrics...";
      }
      if (stage2Progress >= 75) {
        message = "Stage 2: Finalizing cross-source data joins...";
      }
      if (stage2Progress >= 85) {
        message = "Stage 2: Completing fraud pattern analysis...";
      }
      
      updateProgress(Math.round(stage2Progress), message);
    }, 2000); // Update every 2 seconds
    
    // Send stage 2 request with cookie_ids for optimization
    const stage2Response = await fetch('/api/fraud/stage2', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        cookie_ids: cookieIds,
        min_conversions: 5  // Only analyze cookies with significant activity
      })
    });
    
    const stage2ResultData = await stage2Response.json();
    
    if (stage2Response.ok && stage2ResultData.fraud_data) {
      stage2Result = stage2ResultData;
      stage2Complete = true;
      
      // If progress interval is not running anymore, handle completion immediately
      if (!progressInterval) {
        updateProgress(90, "Stage 2 complete - Enhancing table with publisher data...");
        
        setTimeout(() => {
          updateProgress(100, "Analysis complete - Enhanced view ready");
          enhanceFraudDataWithStage2(stage2Result);
          
          // Hide the progress bar after completion
          setTimeout(() => {
            hideProgressBar();
          }, 2000);
        }, 500);
      }
      
    } else {
      throw new Error(stage2ResultData.error || "Failed to load stage 2 fraud data");
    }
    
  } catch (error) {
    console.error("Error in stage 2:", error);
    stage2Complete = true;
    stage2Error = error.message;
    
    // Clear interval if it's still running
    if (progressInterval) {
      clearInterval(progressInterval);
    }
    
    updateProgress(100, "Stage 1 complete - Stage 2 enhancement failed");
    console.warn("Stage 2 enhancement failed, showing Stage 1 data only:", error.message);
    
    // Hide the progress bar after failure
    setTimeout(() => {
      hideProgressBar();
    }, 2000);
  }
}

/**
 * Convert stage 1 data to basic fraud data format for immediate display
 */
function convertStage1ToFraudData(stage1Data) {
  return stage1Data.map(item => ({
    cookie_id: item.cookie_id,
    total_conversions_last_minute: item.conversion_count,
    unique_publishers_last_90m: null, // Will be filled in stage 2
    sample_publishers_90m: null,      // Will be filled in stage 2
    stage1_only: true // Flag to indicate this is stage 1 data only
  }));
}

/**
 * Render initial fraud data from stage 1
 */
function renderInitialFraudData(basicFraudData, stage1Response) {
  fraudData = basicFraudData;
  filteredData = [...fraudData];
  
  // Update metadata with stage 1 info
  updateElement('last-updated', new Date(stage1Response.timestamp).toLocaleString());
  updateElement('analysis-window', "Stage 1: Last minute conversions (Stage 2 loading...)");
  
  // Update summary cards based on stage 1 data only
  updateSummaryCardsFromStage1(basicFraudData);
  
  // Render the table with stage 1 data
  renderFraudTable();
  
  // Show dashboard immediately with global progress bar
  hideElement('loading');
  showElement('dashboard');
  
  console.log(`Loaded ${fraudData.length} stage 1 fraud detection records`);
}

/**
 * Enhance existing fraud data with stage 2 results
 */
function enhanceFraudDataWithStage2(stage2Response) {
  const stage2Data = stage2Response.fraud_data;
  
  // Create a lookup map for stage 2 data
  const stage2Map = new Map();
  stage2Data.forEach(item => {
    stage2Map.set(item.cookie_id, item);
  });
  
  // Only keep fraud data that exists in both stage 1 AND stage 2
  // Stage 1-only items are considered false positives and should be removed
  fraudData = fraudData.filter(fraudItem => {
    return stage2Map.has(fraudItem.cookie_id);
  }).map(fraudItem => {
    const stage2Info = stage2Map.get(fraudItem.cookie_id);
    return {
      ...fraudItem,
      unique_publishers_last_90m: stage2Info.unique_publishers_last_90m,
      sample_publishers_90m: stage2Info.sample_publishers_90m,
      stage1_only: false // Remove the stage 1 flag
    };
  });
  
  // Add any new cookies that appeared in stage 2 but not stage 1
  stage2Data.forEach(stage2Item => {
    const existsInFiltered = fraudData.some(item => item.cookie_id === stage2Item.cookie_id);
    if (!existsInFiltered) {
      fraudData.push({
        ...stage2Item,
        stage1_only: false
      });
    }
  });
  
  // Update filtered data
  filteredData = [...fraudData];
  
  // Update summary cards with complete data
  updateSummaryCards(stage2Response.summary);
  
  // Update metadata
  updateElement('last-updated', new Date(stage2Response.last_updated).toLocaleString());
  updateElement('analysis-window', stage2Response.analysis_window);
  
  // Update global status
  const globalStatusText = document.getElementById('global-status-text');
  if (globalStatusText) {
    globalStatusText.textContent = 'Analysis complete - Enhanced fraud detection active';
  }
  
  // Re-render the table with enhanced data
  renderFraudTable();
  
  console.log(`Enhanced ${fraudData.length} fraud detection records with stage 2 data (false positives removed)`);
}

/**
 * Update summary cards based on stage 1 data only
 */
function updateSummaryCardsFromStage1(basicFraudData) {
  // Calculate summary from stage 1 data
  const counts = {
    high: 0,
    medium: 0,
    low: 0,
    clean: 0
  };
  
  basicFraudData.forEach(fraud => {
    const riskLevel = calculateRiskLevel(fraud);
    counts[riskLevel]++;
  });
  
  updateElement('high-risk-count', counts.high);
  updateElement('medium-risk-count', counts.medium);
  updateElement('low-risk-count', counts.low);
  updateElement('clean-count', counts.clean);
}

/**
 * Hide the progress bar after analysis completion
 */
function hideProgressBar() {
  // Find the global progress bar container by searching for the element with the specific structure
  const globalProgressBar = document.getElementById('global-progress-bar');
  if (globalProgressBar) {
    // Navigate up to find the card container
    const cardContainer = globalProgressBar.closest('.card');
    if (cardContainer) {
      cardContainer.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
      cardContainer.style.opacity = '0';
      cardContainer.style.transform = 'translateY(-10px)';
      
      setTimeout(() => {
        cardContainer.style.display = 'none';
      }, 500);
    }
  }
}

/**
 * Update progress bar with specific percentage and message
 */
function updateProgress(percentage, message) {
  const progressBar = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-percentage');
  const globalProgressBar = document.getElementById('global-progress-bar');
  const globalProgressText = document.getElementById('global-progress-percentage');
  const globalStatusText = document.getElementById('global-status-text');
  
  // Update loading section progress bar (if visible)
  if (progressBar) {
    progressBar.style.width = `${percentage}%`;
    progressBar.setAttribute('aria-valuenow', percentage);
  }
  if (progressText) {
    progressText.textContent = `${percentage}% - ${message}`;
  }
  
  // Update global progress bar
  if (globalProgressBar) {
    globalProgressBar.style.width = `${percentage}%`;
    globalProgressBar.setAttribute('aria-valuenow', percentage);
    
    // Keep consistent styling throughout
    globalProgressBar.className = 'progress-bar progress-bar-striped progress-bar-animated bg-primary';
  }
  
  if (globalProgressText) {
    globalProgressText.textContent = `${percentage}%`;
  }
  
  if (globalStatusText) {
    globalStatusText.textContent = message;
  }
}

/**
 * Get progress stage message based on completion percentage
 */
function getProgressStage(progress) {
  if (progress < 20) {
    return "Initializing fraud detection queries...";
  } else if (progress < 40) {
    return "Analyzing click patterns and behaviors...";
  } else if (progress < 60) {
    return "Detecting suspicious conversion patterns...";
  } else if (progress < 80) {
    return "Cross-referencing publisher data...";
  } else if (progress < 95) {
    return "Calculating risk scores...";
  } else {
    return "Finalizing fraud analysis...";
  }
}

/**
 * Render fraud detection data in the dashboard
 */
function renderFraudData(data) {
  fraudData = data.fraud_data || [];
  filteredData = [...fraudData];
  
  // Update summary cards
  updateSummaryCards(data.summary);
  
  // Update metadata
  updateElement('last-updated', new Date(data.last_updated).toLocaleString());
  updateElement('analysis-window', data.analysis_window);
  
  // Render the table
  renderFraudTable();
  
  // Show dashboard content
  hideElement('loading');
  showElement('dashboard');
  
  console.log(`Loaded ${fraudData.length} fraud detection records`);
}

/**
 * Update summary cards with fraud counts
 */
function updateSummaryCards(summary) {
  // If summary is provided from backend, use it
  if (summary) {
    updateElement('high-risk-count', summary.high || 0);
    updateElement('medium-risk-count', summary.medium || 0);
    updateElement('low-risk-count', summary.low || 0);
    updateElement('clean-count', summary.clean || 0);
  } else {
    // Calculate summary from fraud data
    const counts = {
      high: 0,
      medium: 0,
      low: 0,
      clean: 0
    };
    
    fraudData.forEach(fraud => {
      const riskLevel = calculateRiskLevel(fraud);
      counts[riskLevel]++;
    });
    
    updateElement('high-risk-count', counts.high);
    updateElement('medium-risk-count', counts.medium);
    updateElement('low-risk-count', counts.low);
    updateElement('clean-count', counts.clean);
  }
}

/**
 * Render the fraud detection table
 */
function renderFraudTable() {
  const tableBody = document.getElementById('fraud-table-body');
  const noResults = document.getElementById('no-results');
  
  if (!tableBody) {
    console.error('Fraud table body not found');
    return;
  }
  
  // Clear existing content
  tableBody.innerHTML = '';
  
  if (filteredData.length === 0) {
    showElement('no-results');
    updateTableCounts(0, fraudData.length);
    return;
  }
  
  hideElement('no-results');
  
  // Create table rows
  filteredData.forEach((fraud, index) => {
    const row = createFraudTableRow(fraud, index);
    tableBody.appendChild(row);
  });
  
  // Update table counts
  updateTableCounts(filteredData.length, fraudData.length);
}

/**
 * Create a table row for fraud data
 */
function createFraudTableRow(fraud, index) {
  const row = document.createElement('tr');
  row.className = 'table-row-enter';
  
  // Add a special class if this is stage 1 only data
  if (fraud.stage1_only) {
    row.classList.add('stage1-only');
  }
  
  // Risk level badge (calculated based on conversion patterns)
  const riskLevel = calculateRiskLevel(fraud);
  const riskBadge = `<span class="risk-badge risk-${riskLevel}">
    <i class="bi bi-${getRiskIcon(riskLevel)} me-1"></i>
    ${riskLevel.toUpperCase()}
  </span>`;
  
  // Cookie ID
  const cookieId = `<code class="cookie-id">${fraud.cookie_id}</code>`;
  
  // Conversion patterns analysis
  let conversionInfo;
  if (fraud.stage1_only) {
    // Stage 1 only - show basic conversion info with loading indicator
    conversionInfo = `
      <div class="conversion-metrics">
        <div><strong>Last Minute:</strong> ${fraud.total_conversions_last_minute} conversions</div>
        <div class="text-muted">
          <small><i class="spinner-border spinner-border-sm me-1" role="status"></i>Loading publisher analysis...</small>
        </div>
      </div>
    `;
  } else {
    // Full stage 2 data available
    conversionInfo = `
      <div class="conversion-metrics">
        <div><strong>Last Minute:</strong> ${fraud.total_conversions_last_minute} conversions</div>
        <div><strong>Publishers (90m):</strong> ${fraud.unique_publishers_last_90m || 0} unique</div>
        ${fraud.sample_publishers_90m && Array.isArray(fraud.sample_publishers_90m) && fraud.sample_publishers_90m.length > 0 ? 
          `<div class="publisher-sample">
            <small>Sample: ${fraud.sample_publishers_90m.slice(0, 3).join(', ')}${fraud.sample_publishers_90m.length > 3 ? '...' : ''}</small>
          </div>` : ''
        }
      </div>
    `;
  }
  
  // Risk score with color coding
  const riskScore = calculateRiskScore(fraud);
  const riskScoreDisplay = `<span class="risk-score ${riskLevel}">${riskScore}</span>`;
  
  // Suspicious patterns based on data analysis
  const suspiciousPatterns = generateSuspiciousPatterns(fraud);
  let patternsList = '';
  if (suspiciousPatterns && suspiciousPatterns.length > 0) {
    const isNormal = suspiciousPatterns.includes('Normal activity');
    const listClass = isNormal ? 'pattern-list' : 'pattern-list';
    patternsList = `<ul class="${listClass}">`;
    suspiciousPatterns.forEach(pattern => {
      const itemClass = pattern === 'Normal activity' ? 'normal' : '';
      patternsList += `<li class="${itemClass}">${pattern}</li>`;
    });
    patternsList += '</ul>';
  }
  
  // Add loading indicator for stage 1 patterns
  if (fraud.stage1_only && patternsList.includes('Normal activity')) {
    patternsList = `
      <div class="text-muted">
        <small><i class="spinner-border spinner-border-sm me-1" role="status"></i>Analyzing patterns...</small>
      </div>
    `;
  }
  
  // Last activity (use current time as placeholder)
  const lastActivity = new Date().toLocaleString();
  
  // Action buttons
  const actions = `
    <button class="btn btn-details action-btn btn-sm mb-2" 
            onclick="showFraudDetails('${fraud.cookie_id}')"
            title="View Details">
      <i class="bi bi-eye"></i> Details
    </button>
    <button class="btn btn-block action-btn btn-sm mb-2" 
            onclick="blockEntity('${fraud.cookie_id}')"
            title="Block Entity"
            ${riskLevel === 'clean' ? 'disabled' : ''}>
      <i class="bi bi-shield-x"></i> Block
    </button>
  `;
  
  row.innerHTML = `
    <td>${riskBadge}</td>
    <td>${cookieId}</td>
    <td>${conversionInfo}</td>
    <td>${patternsList}</td>
    <td>${riskScoreDisplay}</td>
    <td>${lastActivity}</td>
    <td>${actions}</td>
  `;
  
  return row;
}

/**
 * Get Bootstrap icon name for risk level
 */
function getRiskIcon(riskLevel) {
  switch(riskLevel) {
    case 'high': return 'exclamation-triangle-fill';
    case 'medium': return 'exclamation-circle-fill';
    case 'low': return 'info-circle-fill';
    case 'clean': return 'check-circle-fill';
    default: return 'circle-fill';
  }
}

/**
 * Calculate risk level based on conversion patterns
 */
function calculateRiskLevel(fraud) {
  const conversionsLastMinute = fraud.total_conversions_last_minute || 0;
  const uniquePublishers = fraud.unique_publishers_last_90m;
  
  // If stage 2 data not available yet, base risk only on conversions
  if (uniquePublishers === null || uniquePublishers === undefined) {
    if (conversionsLastMinute >= 20) {
      return 'high';
    } else if (conversionsLastMinute >= 10) {
      return 'medium';
    } else if (conversionsLastMinute >= 5) {
      return 'low';
    } else {
      return 'clean';
    }
  }
  
  // Full risk assessment with both metrics
  // High risk: Many conversions in short time with multiple publishers
  if (conversionsLastMinute >= 20 && uniquePublishers >= 10) {
    return 'high';
  }
  // Medium risk: Moderate conversions with several publishers
  if (conversionsLastMinute >= 10 && uniquePublishers >= 5) {
    return 'medium';
  }
  // Low risk: Some unusual activity
  if (conversionsLastMinute >= 5 || uniquePublishers >= 3) {
    return 'low';
  }
  // Clean: Normal activity levels
  return 'clean';
}

/**
 * Calculate numeric risk score
 */
function calculateRiskScore(fraud) {
  const conversionsLastMinute = fraud.total_conversions_last_minute || 0;
  const uniquePublishers = fraud.unique_publishers_last_90m;
  
  // Base score on conversion velocity
  let score = Math.min(conversionsLastMinute * 2, 50); // Max 50 from conversions
  
  // Add publisher diversity score if available
  if (uniquePublishers !== null && uniquePublishers !== undefined) {
    score += Math.min(uniquePublishers * 3, 50); // Max 50 from publishers
  } else {
    // If no publisher data, weight conversions more heavily
    score = Math.min(conversionsLastMinute * 3, 80); // Higher weight for conversions only
  }
  
  return Math.min(score, 100);
}

/**
 * Generate suspicious patterns based on data analysis
 */
function generateSuspiciousPatterns(fraud) {
  const patterns = [];
  const conversionsLastMinute = fraud.total_conversions_last_minute || 0;
  const uniquePublishers = fraud.unique_publishers_last_90m;
  
  // Conversion-based patterns (always available)
  if (conversionsLastMinute >= 20) {
    patterns.push('Extremely high conversion rate');
  } else if (conversionsLastMinute >= 10) {
    patterns.push('High conversion velocity');
  } else if (conversionsLastMinute >= 5) {
    patterns.push('Elevated conversion activity');
  }
  
  // Publisher-based patterns (only if stage 2 data is available)
  if (uniquePublishers !== null && uniquePublishers !== undefined) {
    if (uniquePublishers >= 10) {
      patterns.push('Multiple publisher sources');
    } else if (uniquePublishers >= 5) {
      patterns.push('Diverse publisher activity');
    }
    
    if (conversionsLastMinute >= 15 && uniquePublishers <= 2) {
      patterns.push('Concentrated publisher activity');
    }
    
    if (conversionsLastMinute >= 5 && uniquePublishers >= 8) {
      patterns.push('Distributed conversion pattern');
    }
  }
  
  if (patterns.length === 0) {
    patterns.push('Normal activity');
  }
  
  return patterns;
}

/**
 * Show fraud details in modal
 */
function showFraudDetails(cookieId) {
  const fraud = fraudData.find(f => f.cookie_id === cookieId);
  
  if (!fraud) {
    console.error(`Fraud data not found for cookie ID: ${cookieId}`);
    return;
  }
  
  const modalBody = document.getElementById('fraud-modal-body');
  const modalTitle = document.getElementById('fraudDetailsModalLabel');
  
  if (!modalBody || !modalTitle) {
    console.error('Fraud modal elements not found');
    return;
  }
  
  // Calculate risk assessment
  const riskLevel = calculateRiskLevel(fraud);
  const riskScore = calculateRiskScore(fraud);
  const suspiciousPatterns = generateSuspiciousPatterns(fraud);
  
  // Update modal title
  modalTitle.textContent = `Fraud Details - ${fraud.cookie_id}`;
  
  // Create detailed content
  const patternsList = suspiciousPatterns.map(pattern => 
    `<li class="${pattern === 'Normal activity' ? 'normal' : ''}">${pattern}</li>`
  ).join('');
  
  modalBody.innerHTML = `
    <div class="fraud-detail-section">
      <h6><i class="bi bi-info-circle"></i> Basic Information</h6>
      <table class="table table-sm detail-table">
        <tr>
          <th>Cookie ID</th>
          <td><code>${fraud.cookie_id}</code></td>
        </tr>
        <tr>
          <th>Risk Level</th>
          <td><span class="risk-badge risk-${riskLevel}">${riskLevel.toUpperCase()}</span></td>
        </tr>
        <tr>
          <th>Risk Score</th>
          <td><span class="risk-score ${riskLevel}">${riskScore}/100</span></td>
        </tr>
      </table>
    </div>
    
    <div class="fraud-detail-section">
      <h6><i class="bi bi-graph-up"></i> Conversion Analysis</h6>
      <table class="table table-sm detail-table">
        <tr>
          <th>Conversions (Last Minute)</th>
          <td><strong>${fraud.total_conversions_last_minute || 0}</strong></td>
        </tr>
        <tr>
          <th>Unique Publishers (90min)</th>
          <td><strong>${fraud.unique_publishers_last_90m || 0}</strong></td>
        </tr>
        <tr>
          <th>Sample Publishers</th>
          <td>
            ${fraud.sample_publishers_90m && Array.isArray(fraud.sample_publishers_90m) && fraud.sample_publishers_90m.length > 0 ? 
              fraud.sample_publishers_90m.join(', ') : 'No publisher data'
            }
          </td>
        </tr>
      </table>
    </div>
    
    <div class="fraud-detail-section">
      <h6><i class="bi bi-exclamation-triangle"></i> Detected Patterns</h6>
      <ul class="pattern-list">
        ${patternsList}
      </ul>
    </div>
    
    <div class="fraud-detail-section">
      <h6><i class="bi bi-shield-check"></i> Risk Assessment</h6>
      <div class="progress mb-2" style="height: 20px;">
        <div class="progress-bar bg-${riskLevel === 'high' ? 'danger' : riskLevel === 'medium' ? 'warning' : riskLevel === 'low' ? 'info' : 'success'}" 
             role="progressbar" 
             style="width: ${riskScore}%"
             aria-valuenow="${riskScore}" 
             aria-valuemin="0" 
             aria-valuemax="100">
          ${riskScore}%
        </div>
      </div>
      <p class="text-muted small">
        Risk assessment based on conversion velocity, publisher diversity, and pattern analysis.
      </p>
    </div>
  `;
  
  // Update block button
  const blockBtn = document.getElementById('block-entity-btn');
  if (blockBtn) {
    blockBtn.disabled = riskLevel === 'clean';
    blockBtn.onclick = () => blockEntity(fraud.cookie_id);
  }
  
  // Show modal
  const modal = new bootstrap.Modal(document.getElementById('fraudDetailsModal'));
  modal.show();
}

/**
 * Block entity (placeholder functionality)
 */
function blockEntity(cookieId) {
  // This would integrate with actual blocking system
  console.log(`Blocking entity with cookie ID: ${cookieId}`);
  
  // Show confirmation
  if (confirm(`Are you sure you want to block entity ${cookieId}? This action cannot be undone.`)) {
    // Simulate blocking action
    alert(`Entity ${cookieId} has been blocked successfully.`);
    
    // Close modal if open
    const modal = bootstrap.Modal.getInstance(document.getElementById('fraudDetailsModal'));
    if (modal) {
      modal.hide();
    }
  }
}

/**
 * Filter fraud data based on risk level
 */
function filterByRiskLevel(riskLevel) {
  currentRiskFilter = riskLevel;
  applyFilters();
}

/**
 * Search fraud data
 */
function searchFraudData(searchTerm) {
  currentSearchTerm = searchTerm.toLowerCase();
  applyFilters();
}

/**
 * Apply current filters to fraud data
 */
function applyFilters() {
  filteredData = fraudData.filter(fraud => {
    const riskLevel = calculateRiskLevel(fraud);
    const suspiciousPatterns = generateSuspiciousPatterns(fraud);
    
    // Risk level filter
    const matchesRisk = !currentRiskFilter || riskLevel === currentRiskFilter;
    
    // Search filter
    const matchesSearch = !currentSearchTerm || 
      fraud.cookie_id.toLowerCase().includes(currentSearchTerm) ||
      suspiciousPatterns.some(pattern => 
        pattern.toLowerCase().includes(currentSearchTerm)
      ) ||
      (fraud.sample_publishers_90m && Array.isArray(fraud.sample_publishers_90m) && fraud.sample_publishers_90m.some(pub => 
        pub.toLowerCase().includes(currentSearchTerm)
      ));
    
    return matchesRisk && matchesSearch;
  });
  
  renderFraudTable();
}

/**
 * Update table count display
 */
function updateTableCounts(showing, total) {
  updateElement('showing-count', showing);
  updateElement('total-count', total);
}

/**
 * Export fraud data (updated for new structure)
 */
function exportFraudData() {
  console.log('Exporting fraud data...');
  
  // Create CSV content with new fields
  const headers = ['Risk Level', 'Cookie ID', 'Conversions Last Minute', 'Unique Publishers 90m', 'Sample Publishers', 'Suspicious Patterns', 'Risk Score'];
  const csvContent = [
    headers.join(','),
    ...filteredData.map(fraud => {
      const riskLevel = calculateRiskLevel(fraud);
      const riskScore = calculateRiskScore(fraud);
      const suspiciousPatterns = generateSuspiciousPatterns(fraud);
      
      return [
        riskLevel,
        fraud.cookie_id,
        fraud.total_conversions_last_minute || 0,
        fraud.unique_publishers_last_90m || 0,
        `"${(fraud.sample_publishers_90m || []).join('; ')}"`,
        `"${suspiciousPatterns.join('; ')}"`,
        riskScore
      ].join(',');
    })
  ].join('\n');
  
  // Create and download file
  const blob = new Blob([csvContent], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `fraud_detection_${new Date().toISOString().split('T')[0]}.csv`;
  a.click();
  window.URL.revokeObjectURL(url);
}

/**
 * Show loading state
 */
function showLoadingState() {
  hideElement('dashboard');
  hideElement('error');
  showElement('loading');
  
  // Reset progress bar
  const progressBar = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-percentage');
  
  if (progressBar) {
    progressBar.style.width = '0%';
    progressBar.setAttribute('aria-valuenow', '0');
  }
  if (progressText) {
    progressText.textContent = '0% - Initializing fraud detection...';
  }
}

/**
 * Show error state
 */
function showError(message) {
  hideElement('loading');
  hideElement('dashboard');
  
  const errorEl = document.getElementById('error');
  const errorMessageEl = document.getElementById('error-message');
  
  if (errorEl && errorMessageEl) {
    errorMessageEl.textContent = message;
    errorEl.classList.remove('d-none');
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
    element.classList.add('d-none');
  }
}

function showElement(id) {
  const element = document.getElementById(id);
  if (element) {
    element.classList.remove('d-none');
  }
}

/**
 * Initialize event listeners
 */
function initializeFraudDashboard() {
  // Risk filter dropdown
  const riskFilter = document.getElementById('risk-filter');
  if (riskFilter) {
    riskFilter.addEventListener('change', (e) => {
      filterByRiskLevel(e.target.value);
    });
  }
  
  // Search input
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchFraudData(e.target.value);
    });
  }
  
  // Export button
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', exportFraudData);
  }
  
  // Load initial data
  loadFraudData();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeFraudDashboard);
} else {
  initializeFraudDashboard();
}