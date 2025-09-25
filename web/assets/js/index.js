/**
 * Index Page JavaScript
 * Handles index page specific functionality like the fetch button
 */

/**
 * Handle fetch button click to demonstrate API call
 */
async function handleFetchButtonClick() {
  try {
    const res = await fetch("/api");
    const data = await res.json();
    const responseEl = document.getElementById("response");
    
    if (responseEl) {
      responseEl.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
    }
  } catch (error) {
    console.error("Error fetching API data:", error);
    const responseEl = document.getElementById("response");
    if (responseEl) {
      responseEl.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
  }
}

/**
 * Initialize the index page
 */
function initializeIndexPage() {
  // Set up fetch button click handler
  const fetchBtn = document.getElementById("fetchBtn");
  if (fetchBtn) {
    fetchBtn.addEventListener("click", handleFetchButtonClick);
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeIndexPage);
} else {
  initializeIndexPage();
}