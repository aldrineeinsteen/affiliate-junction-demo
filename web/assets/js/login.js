// Login form handling
document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const errorMessage = document.getElementById('errorMessage');
    const errorText = document.getElementById('errorText');
    const loginButton = document.getElementById('loginButton');
    const loginButtonText = loginButton.querySelector('.login-button-text');
    const loginButtonLoading = loginButton.querySelector('.login-button-loading');

    // Handle form submission
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(loginForm);
        const username = formData.get('username');
        const password = formData.get('password');
        
        // Validate inputs
        if (!username || !password) {
            showError('Please enter both username and password');
            return;
        }
        
        // Show loading state
        setLoadingState(true);
        hideError();
        
        try {
            // Send login request
            const response = await fetch('/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // Login successful - redirect to the intended page or home
                const urlParams = new URLSearchParams(window.location.search);
                const redirectUrl = urlParams.get('redirect') || '/';
                window.location.href = redirectUrl;
            } else {
                // Login failed
                showError(result.message || 'Invalid username or password');
            }
            
        } catch (error) {
            console.error('Login error:', error);
            showError('Login failed. Please try again.');
        } finally {
            setLoadingState(false);
        }
    });
    
    // Show error message
    function showError(message) {
        errorText.textContent = message;
        errorMessage.classList.remove('d-none');
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    
    // Hide error message
    function hideError() {
        errorMessage.classList.add('d-none');
    }
    
    // Set loading state
    function setLoadingState(isLoading) {
        loginButton.disabled = isLoading;
        
        if (isLoading) {
            loginButtonText.classList.add('d-none');
            loginButtonLoading.classList.remove('d-none');
        } else {
            loginButtonText.classList.remove('d-none');
            loginButtonLoading.classList.add('d-none');
        }
    }
    
    // Clear error message when user starts typing
    const inputs = loginForm.querySelectorAll('input');
    inputs.forEach(input => {
        input.addEventListener('input', hideError);
    });
    
    // Focus on username field when page loads
    document.getElementById('username').focus();
});