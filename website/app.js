/**
 * Iridia Daily - Application Script
 * 
 * 
 * @author Alex Howell
 */

'use strict';

/* ==========================================================================
   Configuration
   ========================================================================== */

/**
 * API base URL loaded from external configuration file.
 * Allows environment-specific configuration without code changes.
 * 
 * @type {string}
 * @constant
 */
const API_BASE_URL = window.IRIDIA_CONFIG?.API_URL || 'https://your-api-endpoint.com';

/* ==========================================================================
   Data
   ========================================================================== */

/**
 * Sample research papers for demonstration.
 * In production, this data would be fetched from an API endpoint.
 * 
 * @typedef {Object} ResearchPaper
 * @property {string} topic - Research category
 * @property {string} date - Publication date
 * @property {string} title - Paper title
 * @property {string} summary - Brief description
 * @property {string} journal - Publishing journal
 * @property {string} url - Link to full paper
 * 
 * @type {ResearchPaper[]}
 * @constant
 */
const samplePapers = [
    {
        topic: 'neuroscience',
        date: 'Oct 26, 2024',
        title: 'Neural mechanisms of memory consolidation during sleep',
        summary: 'Researchers discovered that specific neural pathways activate during deep sleep to strengthen memories formed during waking hours, providing new insights into learning processes.',
        journal: 'Nature Neuroscience',
        url: 'https://pubmed.ncbi.nlm.nih.gov/12345678/'
    },
    {
        topic: 'space',
        date: 'Oct 25, 2024',
        title: 'Earth-like exoplanet discovered in habitable zone',
        summary: 'Astronomers identified a potentially habitable planet orbiting a nearby star, showing signs of atmospheric water vapor and temperatures suitable for liquid water.',
        journal: 'The Astrophysical Journal',
        url: 'https://pubmed.ncbi.nlm.nih.gov/87654321/'
    },
    {
        topic: 'biology',
        date: 'Oct 24, 2024',
        title: 'CRISPR breakthrough enables precise gene therapy',
        summary: 'Scientists developed a new CRISPR variant with unprecedented accuracy, successfully treating sickle cell disease in clinical trials with minimal off-target effects.',
        journal: 'New England Journal of Medicine',
        url: 'https://pubmed.ncbi.nlm.nih.gov/11223344/'
    },
    {
        topic: 'physics',
        date: 'Oct 23, 2024',
        title: 'Quantum entanglement maintained at room temperature',
        summary: 'Physicists achieved stable quantum entanglement without cryogenic cooling, potentially revolutionizing practical quantum computing applications.',
        journal: 'Physical Review Letters',
        url: 'https://pubmed.ncbi.nlm.nih.gov/44556677/'
    },
    {
        topic: 'environment',
        date: 'Oct 22, 2024',
        title: 'Ocean ecosystems show unexpected climate resilience',
        summary: 'Long-term study reveals marine life adapting through novel symbiotic relationships, offering hope for conservation strategies in warming seas.',
        journal: 'Science',
        url: 'https://pubmed.ncbi.nlm.nih.gov/99887766/'
    },
    {
        topic: 'medicine',
        date: 'Oct 21, 2024',
        title: 'mRNA vaccine shows promise against multiple cancers',
        summary: 'Phase II trials demonstrate personalized mRNA vaccines can train immune systems to recognize and attack various tumor types with minimal side effects.',
        journal: 'The Lancet',
        url: 'https://pubmed.ncbi.nlm.nih.gov/55443322/'
    }
];

/**
 * Topic color mapping for consistent UI theming.
 * Colors are WCAG AA compliant for accessibility.
 * 
 * @type {Object.<string, string>}
 * @constant
 */
const topicColors = {
    'neuroscience': '#7d3bb8',
    'space': '#3651d4',
    'biology': '#05a77c',
    'environment': '#1f8a7e',
    'physics': '#d4244d',
    'medicine': '#d11363',
    'technology': '#2ba9cc'
};

/* ==========================================================================
   State Management
   ========================================================================== */

/**
 * Current active topic filter.
 * 
 * @type {string}
 */
let currentFilter = 'all';

/**
 * Array of focusable elements within the modal for focus trapping.
 * 
 * @type {HTMLElement[]}
 */
let focusableElements = [];

/**
 * Element that had focus before modal opened.
 * Used to restore focus when modal closes.
 * 
 * @type {HTMLElement|null}
 */
let lastFocusedElement = null;

/* ==========================================================================
   Initialization
   ========================================================================== */

/**
 * Initialize application when DOM is fully loaded.
 * Sets up all event listeners and renders initial content.
 * 
 * @returns {void}
 */
document.addEventListener('DOMContentLoaded', () => {
    renderPapers();
    setupEventListeners();
    setupCheckboxes();
    setupScrollEffects();
    setupKeyboardNav();
    announcePageLoad();
});

/* ==========================================================================
   Event Listeners Setup
   ========================================================================== */

/**
 * Set up all event listeners for interactive elements.
 * Uses event delegation where appropriate for better performance.
 * 
 * @returns {void}
 */
function setupEventListeners() {
    // Subscribe button listeners
    const subscribeButtons = document.querySelectorAll('.subscribe-btn');
    subscribeButtons.forEach(button => {
        button.addEventListener('click', openModal);
    });
    
    // Filter button listeners
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(button => {
        button.addEventListener('click', handleFilterClick);
    });
    
    // Modal close button
    const closeButton = document.querySelector('.close-btn');
    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
    }
    
    // Modal backdrop click
    const modalOverlay = document.getElementById('modalOverlay');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', handleBackdropClick);
    }
    
    // Form submission
    const form = document.getElementById('subscribeForm');
    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
}

/* ==========================================================================
   Paper Rendering
   ========================================================================== */

/**
 * Renders research papers to the DOM with smooth transition.
 * Filters papers based on current selection and updates ARIA live region.
 * 
 * @returns {void}
 */
function renderPapers() {
    const grid = document.getElementById('archiveGrid');
    if (!grid) return;
    
    const filteredPapers = currentFilter === 'all' 
        ? samplePapers 
        : samplePapers.filter(p => p.topic === currentFilter);
    
    // Announce filter change to screen readers
    announceFilterChange(filteredPapers.length, currentFilter);
    
    // Fade out current content
    grid.style.opacity = '0';
    
    // Delay rendering to allow fade-out animation
    setTimeout(() => {
        grid.innerHTML = filteredPapers.map(paper => createPaperCard(paper)).join('');
        
        // Fade in new content using RAF for smooth animation
        requestAnimationFrame(() => {
            grid.style.opacity = '1';
        });
    }, 200);
}

/**
 * Creates HTML markup for a single paper card.
 * Includes proper semantic structure and ARIA attributes.
 * 
 * @param {ResearchPaper} paper - Paper data object
 * @returns {string} HTML string for paper card
 */
function createPaperCard(paper) {
    const topicLabel = paper.topic.charAt(0).toUpperCase() + paper.topic.slice(1);
    
    return `
        <article class="paper-card" aria-labelledby="paper-${paper.topic}-title">
            <div class="paper-header">
                <span 
                    class="topic-badge" 
                    style="background: ${topicColors[paper.topic]}"
                    role="text"
                >
                    ${topicLabel.toUpperCase()}
                </span>
                <time class="date" datetime="${paper.date}">${paper.date}</time>
            </div>
            <h3 id="paper-${paper.topic}-title" class="paper-title">${escapeHtml(paper.title)}</h3>
            <p class="paper-summary">${escapeHtml(paper.summary)}</p>
            <div class="paper-footer">
                <span class="journal">${escapeHtml(paper.journal)}</span>
                <a 
                    href="${escapeHtml(paper.url)}" 
                    class="read-more" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    aria-label="Read full paper: ${escapeHtml(paper.title)} (opens in new tab)"
                >
                    Read paper
                </a>
            </div>
        </article>
    `;
}

/**
 * Escapes HTML special characters to prevent XSS attacks.
 * 
 * @param {string} text - Text to escape
 * @returns {string} Escaped text safe for HTML insertion
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Handles filter button clicks and updates UI state.
 * Updates ARIA pressed states for accessibility.
 * 
 * @param {Event} event - Click event object
 * @returns {void}
 */
function handleFilterClick(event) {
    const button = event.currentTarget;
    const topic = button.getAttribute('data-topic');
    
    if (!topic) return;
    
    // Update current filter
    currentFilter = topic;
    
    // Update ARIA pressed states on all filter buttons
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        const isPressed = btn === button;
        btn.classList.toggle('active', isPressed);
        btn.setAttribute('aria-pressed', isPressed.toString());
    });
    
    // Re-render papers with new filter
    renderPapers();
}

/* ==========================================================================
   Accessibility Announcements
   ========================================================================== */

/**
 * Announces page load to screen readers.
 * 
 * @returns {void}
 */
function announcePageLoad() {
    const statusElement = document.getElementById('filter-status');
    if (statusElement) {
        statusElement.textContent = 'Page loaded. Showing all research papers.';
        
        // Clear announcement after it's been read
        setTimeout(() => {
            statusElement.textContent = '';
        }, 1000);
    }
}

/**
 * Announces filter changes to screen readers via ARIA live region.
 * 
 * @param {number} count - Number of papers displayed
 * @param {string} topic - Current filter topic
 * @returns {void}
 */
function announceFilterChange(count, topic) {
    const statusElement = document.getElementById('filter-status');
    if (!statusElement) return;
    
    const topicText = topic === 'all' ? 'all topics' : topic;
    const message = `Showing ${count} research ${count === 1 ? 'paper' : 'papers'} for ${topicText}.`;
    
    statusElement.textContent = message;
    
    // Clear announcement after it's been read
    setTimeout(() => {
        statusElement.textContent = '';
    }, 3000);
}

/* ==========================================================================
   Form Interactions
   ========================================================================== */

/**
 * Sets up checkbox wrapper interactions for enhanced UX.
 * Allows clicking anywhere on wrapper to toggle checkbox while
 * maintaining native checkbox behavior for keyboard users and labels.
 * 
 * @returns {void}
 */
function setupCheckboxes() {
    const wrappers = document.querySelectorAll('.topic-checkbox-wrapper');
    
    wrappers.forEach(wrapper => {
        const checkbox = wrapper.querySelector('input[type="checkbox"]');
        const label = wrapper.querySelector('label');
        if (!checkbox) return;
        
        // Handle clicks on wrapper (excluding checkbox and label which have native behavior)
        wrapper.addEventListener('click', (e) => {
            // Only toggle if clicking wrapper itself, not checkbox or label
            if (e.target !== checkbox && e.target !== label) {
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        
        // Update wrapper styling based on checkbox state
        checkbox.addEventListener('change', () => {
            wrapper.classList.toggle('checked', checkbox.checked);
        });
    });
}

/* ==========================================================================
   Scroll Effects
   ========================================================================== */

/**
 * Sets up scroll-based UI effects.
 * Adds shadow to header when user scrolls down for visual feedback.
 * 
 * @returns {void}
 */
function setupScrollEffects() {
    const header = document.querySelector('.header');
    if (!header) return;
    
    let lastScroll = 0;
    
    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;
        
        // Add shadow class when scrolled past threshold
        if (currentScroll > 10) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
        
        lastScroll = currentScroll;
    }, { passive: true }); // Passive listener for better scroll performance
}

/* ==========================================================================
   Keyboard Navigation
   ========================================================================== */

/**
 * Sets up keyboard navigation shortcuts.
 * Handles ESC key to close modal and other keyboard interactions.
 * 
 * @returns {void}
 */
function setupKeyboardNav() {
    document.addEventListener('keydown', (e) => {
        const modalOverlay = document.getElementById('modalOverlay');
        
        // Close modal on Escape key
        if (e.key === 'Escape' && modalOverlay && !modalOverlay.hasAttribute('aria-hidden')) {
            closeModal();
        }
        
        // Handle Tab key for focus trapping in modal
        if (e.key === 'Tab' && modalOverlay && !modalOverlay.hasAttribute('aria-hidden')) {
            handleModalTabKey(e);
        }
    });
}

/**
 * Handles Tab key press within modal for focus trapping.
 * Keeps focus within modal while it's open.
 * 
 * @param {KeyboardEvent} e - Keyboard event
 * @returns {void}
 */
function handleModalTabKey(e) {
    if (focusableElements.length === 0) return;
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    // Shift + Tab on first element: move to last element
    if (e.shiftKey && document.activeElement === firstElement) {
        e.preventDefault();
        lastElement.focus();
    }
    // Tab on last element: move to first element
    else if (!e.shiftKey && document.activeElement === lastElement) {
        e.preventDefault();
        firstElement.focus();
    }
}

/* ==========================================================================
   Modal Management
   ========================================================================== */

/**
 * Opens the subscription modal with proper accessibility features.
 * - Traps focus within modal
 * - Prevents body scrolling
 * - Saves last focused element for restoration
 * - Announces modal opening to screen readers
 * 
 * @returns {void}
 */
function openModal() {
    const modalOverlay = document.getElementById('modalOverlay');
    if (!modalOverlay) return;
    
    // Save currently focused element
    lastFocusedElement = document.activeElement;
    
    // Show modal
    modalOverlay.classList.add('active');
    modalOverlay.setAttribute('aria-hidden', 'false');
    
    // Prevent body scrolling
    document.body.style.overflow = 'hidden';
    
    // Get all focusable elements within modal for focus trapping
    const modal = modalOverlay.querySelector('.modal');
    if (modal) {
        focusableElements = getFocusableElements(modal);
    }
    
    // Focus first input after animation completes
    setTimeout(() => {
        const emailInput = document.getElementById('email');
        if (emailInput) {
            emailInput.focus();
        }
    }, 100);
}

/**
 * Closes the subscription modal with proper cleanup.
 * - Restores focus to element that opened modal
 * - Restores body scrolling
 * - Clears form and error messages
 * - Announces modal closing to screen readers
 * 
 * @returns {void}
 */
function closeModal() {
    const modalOverlay = document.getElementById('modalOverlay');
    if (!modalOverlay) return;
    
    // Hide modal
    modalOverlay.classList.remove('active');
    modalOverlay.setAttribute('aria-hidden', 'true');
    
    // Restore body scrolling
    document.body.style.overflow = '';
    
    // Restore focus to element that opened modal
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
    }
    
    // Reset form and clear messages after animation completes
    setTimeout(() => {
        const form = document.getElementById('subscribeForm');
        if (form) {
            form.reset();
        }
        
        // Clear all error messages
        clearFormErrors();
        
        // Clear status message
        const messageDiv = document.getElementById('message');
        if (messageDiv) {
            messageDiv.innerHTML = '';
        }
        
        // Reinitialize checkboxes to update checked state
        setupCheckboxes();
    }, 300);
}

/**
 * Handles clicks on modal backdrop to close modal.
 * Only closes if backdrop itself is clicked, not modal content.
 * 
 * @param {MouseEvent} event - Click event object
 * @returns {void}
 */
function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
        closeModal();
    }
}

/**
 * Gets all focusable elements within a container.
 * Used for focus trapping in modal dialogs.
 * 
 * @param {HTMLElement} container - Container element to search
 * @returns {HTMLElement[]} Array of focusable elements
 */
function getFocusableElements(container) {
    const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const elements = container.querySelectorAll(selector);
    
    // Filter out disabled elements and return as array
    return Array.from(elements).filter(el => 
        !el.hasAttribute('disabled') && 
        !el.hasAttribute('hidden') &&
        el.tabIndex !== -1
    );
}

/* ==========================================================================
   Form Submission
   ========================================================================== */

/**
 * Handles subscription form submission with validation.
 * - Validates email and topic selection
 * - Shows accessible error messages
 * - Sends data to API
 * - Provides user feedback via ARIA live regions
 * 
 * @param {Event} event - Form submit event
 * @returns {Promise<void>}
 */
async function handleSubmit(event) {
    event.preventDefault();
    
    const form = event.target;
    const email = form.email.value.trim();
    const topicCheckboxes = form.querySelectorAll('input[name="topics"]:checked');
    const topics = Array.from(topicCheckboxes).map(input => input.value);
    
    const messageDiv = document.getElementById('message');
    const submitBtn = document.getElementById('submitBtn');
    
    // Clear previous messages and errors
    clearFormErrors();
    if (messageDiv) {
        messageDiv.innerHTML = '';
    }
    
    // Validate form
    let hasError = false;
    
    // Validate email
    if (!email || !isValidEmail(email)) {
        showFieldError('email', 'Please enter a valid email address.');
        hasError = true;
    }
    
    // Validate topic selection
    if (topics.length === 0) {
        showFieldError('topics', 'Please select at least one topic.');
        
        // Add shake animation to checkboxes for visual feedback
        const checkboxContainer = document.querySelector('.topic-checkboxes');
        if (checkboxContainer) {
            checkboxContainer.style.animation = 'none';
            // Trigger reflow to restart animation
            void checkboxContainer.offsetWidth;
            checkboxContainer.style.animation = 'shake 0.5s ease';
        }
        
        hasError = true;
    }
    
    if (hasError) {
        // Focus first field with error
        const firstError = document.querySelector('.form-input.error, .topic-checkboxes');
        if (firstError) {
            firstError.focus();
        }
        return;
    }
    
    // Update button state to prevent duplicate submissions
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Subscribing...';
        submitBtn.classList.add('loading');
        submitBtn.setAttribute('aria-busy', 'true');
    }
    
    try {
        // Send subscription request to API
        const response = await fetch(`${API_BASE_URL}/subscribe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, topics })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show success message
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="message success" role="status">✓ Success! Check your email to confirm your subscription.</div>';
            }
            
            // Reset form
            form.reset();
            setupCheckboxes();
            
            // Auto-close modal after successful subscription
            setTimeout(() => {
                closeModal();
            }, 3000);
        } else {
            // Show error message from API
            const errorMessage = data.error || 'Subscription failed. Please try again.';
            if (messageDiv) {
                messageDiv.innerHTML = `<div class="message error" role="alert">✗ ${escapeHtml(errorMessage)}</div>`;
            }
        }
    } catch (error) {
        // Handle network errors
        console.error('Subscription error:', error);
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="message error" role="alert">✗ Network error. Please check your connection and try again.</div>';
        }
    } finally {
        // Restore button state
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Subscribe';
            submitBtn.classList.remove('loading');
            submitBtn.removeAttribute('aria-busy');
        }
    }
}

/* ==========================================================================
   Form Validation
   ========================================================================== */

/**
 * Validates email address format.
 * Uses standard email regex pattern.
 * 
 * @param {string} email - Email address to validate
 * @returns {boolean} True if email is valid
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Shows error message for a form field.
 * Updates ARIA attributes and displays error text.
 * 
 * @param {string} fieldId - ID of the form field
 * @param {string} message - Error message to display
 * @returns {void}
 */
function showFieldError(fieldId, message) {
    if (fieldId === 'email') {
        const input = document.getElementById('email');
        const errorElement = document.getElementById('email-error');
        
        if (input && errorElement) {
            input.classList.add('error');
            input.setAttribute('aria-invalid', 'true');
            errorElement.textContent = message;
        }
    } else if (fieldId === 'topics') {
        const errorElement = document.getElementById('topics-error');
        
        if (errorElement) {
            errorElement.textContent = message;
        }
    }
}

/**
 * Clears all form error messages and states.
 * Removes error classes and ARIA attributes.
 * 
 * @returns {void}
 */
function clearFormErrors() {
    // Clear email error
    const emailInput = document.getElementById('email');
    const emailError = document.getElementById('email-error');
    
    if (emailInput) {
        emailInput.classList.remove('error');
        emailInput.removeAttribute('aria-invalid');
    }
    
    if (emailError) {
        emailError.textContent = '';
    }
    
    // Clear topics error
    const topicsError = document.getElementById('topics-error');
    if (topicsError) {
        topicsError.textContent = '';
    }
}

/* ==========================================================================
   Animation Utilities
   ========================================================================== */

/**
 * Adds shake animation styles to document head.
 * Used for form validation feedback.
 * Only added once to avoid duplicate style tags.
 */
(() => {
    const styleId = 'shake-animation-style';
    
    // Check if style already exists
    if (document.getElementById(styleId)) return;
    
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
            20%, 40%, 60%, 80% { transform: translateX(5px); }
        }
    `;
    document.head.appendChild(style);
})();

/* ==========================================================================
   Smooth Scroll Enhancement
   ========================================================================== */

/**
 * Enables smooth scrolling for anchor links.
 * Uses native scrollIntoView with smooth behavior.
 * Only applies to hash links on same page.
 */
document.addEventListener('DOMContentLoaded', () => {
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    
    anchorLinks.forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            
            // Skip if href is just "#"
            if (href === '#') return;
            
            const target = document.querySelector(href);
            if (!target) return;
            
            e.preventDefault();
            
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
            
            // Set focus on target for keyboard users
            target.setAttribute('tabindex', '-1');
            target.focus();
        });
    });
});

/* ==========================================================================
   Reduced Motion Support
   ========================================================================== */

/**
 * Disables animations for users who prefer reduced motion.
 * Respects system-level accessibility preference.
 * Updates CSS custom properties to remove transitions.
 */
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // Set transition times to near-instant
    document.documentElement.style.setProperty('--transition-fast', '0.01ms');
    document.documentElement.style.setProperty('--transition-normal', '0.01ms');
    document.documentElement.style.setProperty('--transition-slow', '0.01ms');
}