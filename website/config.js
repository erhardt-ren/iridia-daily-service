/**
 * Iridia Daily - Application Configuration
 * 
 * Environment-specific configuration settings for the application.
 * Update API_URL with your actual backend endpoint before deployment.
 * 
 * This configuration is loaded before the main application script and
 * provides essential settings needed for API communication.
 * 
 * @version 2.1.0
 * @license MIT
 * @author Iridia Daily Team
 */

/**
 * Global configuration object exposed on window.
 * Contains all environment-specific settings.
 * 
 * @namespace IRIDIA_CONFIG
 * @global
 */
window.IRIDIA_CONFIG = {
    /**
     * Backend API base URL for subscription requests.
     * 
     * This URL should point to your backend server that handles
     * subscription management, user authentication, and other
     * server-side operations.
     * 
     * @memberof IRIDIA_CONFIG
     * @type {string}
     * @default 'https://your-api-endpoint.com'
     * 
     * @example
     * // Production environment
     * API_URL: 'https://api.iridia-daily.com'
     * 
     * @example
     * // Staging environment
     * API_URL: 'https://staging-api.iridia-daily.com'
     * 
     * @example
     * // Local development
     * API_URL: 'http://localhost:3000'
     * 
     * @example
     * // Using environment variables (requires build tool)
     * API_URL: process.env.API_URL || 'http://localhost:3000'
     */
    API_URL: 'https://your-api-endpoint.com',
    
    /**
     * API version string.
     * Used for API versioning and backward compatibility.
     * 
     * @memberof IRIDIA_CONFIG
     * @type {string}
     * @default 'v1'
     */
    API_VERSION: 'v1',
    
    /**
     * Enable debug mode for development.
     * When true, logs additional information to console.
     * 
     * @memberof IRIDIA_CONFIG
     * @type {boolean}
     * @default false
     */
    DEBUG_MODE: false,
    
    /**
     * Request timeout in milliseconds.
     * API requests will fail if they exceed this duration.
     * 
     * @memberof IRIDIA_CONFIG
     * @type {number}
     * @default 30000
     */
    REQUEST_TIMEOUT: 30000,
    
    /**
     * Enable analytics tracking.
     * Set to false to disable all tracking.
     * 
     * @memberof IRIDIA_CONFIG
     * @type {boolean}
     * @default true
     */
    ENABLE_ANALYTICS: true
};

/**
 * Validates the configuration object.
 * Ensures all required settings are present and valid.
 * 
 * @returns {boolean} True if configuration is valid
 * @throws {Error} If configuration is invalid
 */
function validateConfig() {
    const config = window.IRIDIA_CONFIG;
    
    // Check if API_URL is set
    if (!config.API_URL) {
        throw new Error('API_URL must be configured');
    }
    
    // Warn if using default API URL
    if (config.API_URL === 'https://your-api-endpoint.com') {
        console.warn(
            'IRIDIA_CONFIG: Using default API_URL. ' +
            'Please update config.js with your actual backend endpoint.'
        );
    }
    
    // Validate timeout is a positive number
    if (typeof config.REQUEST_TIMEOUT !== 'number' || config.REQUEST_TIMEOUT <= 0) {
        throw new Error('REQUEST_TIMEOUT must be a positive number');
    }
    
    return true;
}

/**
 * Freezes the configuration object to prevent modifications.
 * This ensures configuration remains constant throughout the application lifecycle.
 * 
 * @returns {void}
 */
function freezeConfig() {
    if (Object.freeze) {
        Object.freeze(window.IRIDIA_CONFIG);
    }
}

// Run validation and freeze configuration
try {
    validateConfig();
    freezeConfig();
    
    if (window.IRIDIA_CONFIG.DEBUG_MODE) {
        console.log('IRIDIA_CONFIG loaded successfully:', window.IRIDIA_CONFIG);
    }
} catch (error) {
    console.error('Configuration error:', error.message);
}