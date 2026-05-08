/**
 * Iridia Daily - Application Script
 * 
 * @author Alex Howell
 */

'use strict';

const API_BASE_URL = window.IRIDIA_CONFIG?.API_URL || 'https://your-api-endpoint.com';

// State management
let allPapers = []; // Deprecated - kept for backward compatibility
let currentFilter = 'all';
let currentSearch = '';
let currentSort = 'date_desc';
let currentView = 'list'; // 'list' or 'grid'
let currentPerPage = 10; // Default display count
let currentPage = 1; // Current page number
let totalPages = 1; // Total pages reported by server
let isLastPage = false; // True when server reports no next page

// Pagination window — pages shown on each side of current page.
// Controls width is computed from this value in setupPagination().
const PAGINATION_DELTA = 3;

// Page cache for pre-fetching
let pageCache = new Map(); // Map<pageNumber, {papers, pagination, timestamp}>
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes cache lifetime
let prefetchInProgress = new Set(); // Track ongoing prefetch requests
let currentLoadId = 0; // Incremented on every foreground load; stale responses check against it

let isLoading = false;
let stats = {
    papers_examined: 0,
    papers_returned: 0,
    files_processed: 0
};

const topicColors = {
    neuroscience: '#0ea5e9',
    space: '#8b5cf6',
    biology: '#10b981',
    environment: '#3b82f6',
    physics: '#f59e0b',
    medicine: '#eab308',
    technology: '#ec4899',
    chemistry: '#a855f7',
    default: '#6b7280'
};

let focusableElements = [];
let lastFocusedElement = null;
let searchDebounceTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    loadPage(1); // Load first page
    setupEventListeners();
    setupCheckboxes();
    setupScrollEffects();
    setupKeyboardNav();
    setupSearchBar();
    setupViewToggle();
    setupPagination();
    setupPreviewCard();
    applyViewClass();
});

/**
 * Setup pagination components (top and bottom)
 */
function setupPagination() {
    // Grid columns: prev + ctxLeft + window(2*delta+1) + ctxRight + next
    // ctxLeft is either the page-1 button or the left gap — always occupied, never empty.
    // ctxRight is either the last-page button or the right gap — same.
    const cols = 2 * PAGINATION_DELTA + 5;
    document.documentElement.style.setProperty('--pagination-grid-cols', cols);
    createPaginationComponents();
}

/**
 * Create pagination components at top and bottom of archive grid
 */
function createPaginationComponents() {
    const archiveGrid = document.getElementById('archiveGrid');
    if (!archiveGrid) return;
    
    // Create top pagination - insert into search container
    if (!document.getElementById('paginationTop')) {
        const searchContainer = document.querySelector('.search-container');
        if (searchContainer) {
            const topPagination = createPaginationElement('paginationTop');
            searchContainer.appendChild(topPagination);
        }
    }
    
    // Create bottom pagination
    if (!document.getElementById('paginationBottom')) {
        const bottomPagination = createPaginationElement('paginationBottom');
        archiveGrid.parentNode.insertBefore(bottomPagination, archiveGrid.nextSibling);
    }
    
    updatePaginationDisplay();
}

/**
 * Create a pagination element
 */
function createPaginationElement(id) {
    const container = document.createElement('div');
    container.id = id;
    container.className = 'pagination-container';
    container.setAttribute('role', 'navigation');
    container.setAttribute('aria-label', 'Pagination');
    
    // Info section (showing X papers)
    const info = document.createElement('div');
    info.className = 'pagination-info';
    info.setAttribute('aria-live', 'polite');
    container.appendChild(info);
    
    // Page controls section
    const controls = document.createElement('div');
    controls.className = 'pagination-controls';
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', 'Page navigation');
    container.appendChild(controls);
    
    // Per-page selector section
    const perPageWrapper = document.createElement('div');
    perPageWrapper.className = 'per-page-selector-wrapper';
    
    const label = document.createElement('label');
    label.htmlFor = `perPageSelector-${id}`;
    label.textContent = 'Per page:';
    
    const selector = document.createElement('select');
    selector.id = `perPageSelector-${id}`;
    selector.className = 'per-page-selector';
    selector.setAttribute('aria-label', 'Papers per page');
    
    [10, 25, 50].forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        option.selected = value === currentPerPage;
        selector.appendChild(option);
    });
    
    selector.addEventListener('change', (e) => {
        currentPerPage = parseInt(e.target.value);
        // Update both selectors
        document.querySelectorAll('.per-page-selector').forEach(sel => {
            sel.value = currentPerPage;
        });
        resetAndReload(); // Reload from page 1 with new page size
    });
    
    perPageWrapper.appendChild(label);
    perPageWrapper.appendChild(selector);
    container.appendChild(perPageWrapper);
    
    return container;
}

/**
 * Update pagination display for server-side pagination
 */
function updatePaginationDisplay() {
    const maxVisiblePage = totalPages;
    
    // Update both pagination components
    ['paginationTop', 'paginationBottom'].forEach(id => {
        const container = document.getElementById(id);
        if (!container) return;
        
        // Update info
        const info = container.querySelector('.pagination-info');
        if (info) {
            const cached = pageCache.get(currentPage);
            if (cached && cached.papers) {
                const count = cached.papers.length;
                info.textContent = `Page ${currentPage} of ${totalPages} • ${count} ${count === 1 ? 'paper' : 'papers'}`;
            } else {
                info.textContent = `Page ${currentPage} of ${totalPages}`;
            }
        }
        
        // Update controls
        const controls = container.querySelector('.pagination-controls');
        if (controls) {
            controls.innerHTML = '';
            
            // Previous button — always in grid column 1
            const prevBtn = document.createElement('button');
            prevBtn.className = 'pagination-btn';
            prevBtn.innerHTML = '&laquo;';
            prevBtn.setAttribute('aria-label', 'Previous page');
            prevBtn.disabled = currentPage === 1;
            prevBtn.style.gridColumn = '1';
            prevBtn.addEventListener('click', () => {
                if (currentPage > 1) loadPage(currentPage - 1);
            });
            prevBtn.addEventListener('mouseenter', () => {
                if (currentPage > 1) prefetchPage(currentPage - 1);
            });
            controls.appendChild(prevBtn);

            // Page slots — each element placed into its fixed grid column
            renderPageSlots(controls, currentPage, maxVisiblePage);

            // Next button — always in the last grid column
            const nextBtn = document.createElement('button');
            nextBtn.className = 'pagination-btn';
            nextBtn.innerHTML = '&raquo;';
            nextBtn.setAttribute('aria-label', 'Next page');
            nextBtn.disabled = isLastPage;
            nextBtn.style.gridColumn = String(2 * PAGINATION_DELTA + 5);
            nextBtn.addEventListener('click', () => {
                if (!isLastPage) loadPage(currentPage + 1);
            });
            nextBtn.addEventListener('mouseenter', () => {
                if (!isLastPage) prefetchPage(currentPage + 1);
            });
            controls.appendChild(nextBtn);
        }
    });
}

/**
 * Render page-number slots into the controls element using CSS grid.
 * Each button is assigned an explicit grid-column so its position never shifts.
 *
 * Grid layout (1-indexed):
 *   col 1            : PREV  (set by caller)
 *   col 2            : ctxLeft  — page-1 button (when window is adjacent to page 1)
 *                                OR left-gap "..." (covers pages 1..winStart-1)
 *   cols 3..3+W-1    : window of W = 2*delta+1 pages centred on current
 *   col 3+W          : ctxRight — last-page button (when window is adjacent to last page)
 *                                OR right-gap "..." (covers pages winEnd+1..total)
 *   col 3+W+1        : NEXT  (set by caller)
 *
 * ctxLeft and ctxRight are always occupied, so no empty columns appear between
 * page 1 and the window, or between the window and the last page.
 */
function renderPageSlots(controls, current, total) {
    const delta = PAGINATION_DELTA;
    const W          = 2 * delta + 1;
    const ctxLeftCol = 2;
    const winStartCol = 3;
    const ctxRightCol = 3 + W;   // col right after the window

    // Clamp window to stay within [2, total-1]
    const winStart = Math.max(2, Math.min(current - delta, total - W));
    const winEnd   = winStart + W - 1;

    const makePageBtn = (page, col) => {
        const btn = document.createElement('button');
        btn.className = 'pagination-btn';
        btn.textContent = page;
        btn.setAttribute('aria-label', `Page ${page}`);
        btn.style.gridColumn = String(col);
        if (page === current) {
            btn.classList.add('active');
            btn.setAttribute('aria-current', 'page');
        }
        btn.addEventListener('click', () => loadPage(page));
        btn.addEventListener('mouseenter', () => prefetchPage(page));
        return btn;
    };

    const makeGapBtn = (min, max, col) => {
        const btn = document.createElement('button');
        btn.className = 'pagination-ellipsis pagination-ellipsis-jump';
        btn.textContent = '...';
        btn.setAttribute('aria-label', `Jump to page, range ${min} to ${max}`);
        btn.setAttribute('title', `Click to jump (pages ${min}–${max})`);
        btn.style.gridColumn = String(col);
        btn.addEventListener('click', () => activateJumpInput(btn, min, max));
        return btn;
    };

    // col 2 (ctxLeft): page-1 button when adjacent, otherwise left gap covering page 1
    if (winStart === 2) {
        controls.appendChild(makePageBtn(1, ctxLeftCol));
    } else {
        controls.appendChild(makeGapBtn(1, winStart - 1, ctxLeftCol));
    }

    // cols 3..3+W-1: window pages (skip invalid pages near the edges)
    for (let p = winStart; p <= winEnd; p++) {
        if (p >= 2 && p <= total - 1) {
            controls.appendChild(makePageBtn(p, winStartCol + (p - winStart)));
        }
    }

    // col 3+W (ctxRight): last-page button when adjacent, otherwise right gap covering last page
    if (total > 1) {
        if (winEnd === total - 1) {
            controls.appendChild(makePageBtn(total, ctxRightCol));
        } else {
            controls.appendChild(makeGapBtn(winEnd + 1, total, ctxRightCol));
        }
    }
}

/**
 * Replace an ellipsis button with an inline number input for page jumping.
 * Commits on Enter or blur; cancels on Escape or invalid value.
 */
function activateJumpInput(ellipsisEl, min, max) {
    // Wrapper sits in the same grid cell as the gap button
    const wrapper = document.createElement('div');
    wrapper.className = 'pagination-jump-wrapper';
    wrapper.style.gridColumn = ellipsisEl.style.gridColumn;

    // Tooltip above showing valid range
    const tooltip = document.createElement('span');
    tooltip.className = 'pagination-jump-tooltip';
    tooltip.textContent = `${min}–${max}`;
    wrapper.appendChild(tooltip);

    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'pagination-jump-input';
    input.min = min;
    input.max = max;
    input.setAttribute('aria-label', `Jump to page (${min}–${max})`);
    wrapper.appendChild(input);

    ellipsisEl.replaceWith(wrapper);
    input.focus();

    let settled = false;

    const commit = () => {
        if (settled) return;
        settled = true;
        const value = parseInt(input.value);
        if (value >= min && value <= max) {
            loadPage(value);
        } else {
            wrapper.replaceWith(ellipsisEl);
        }
    };

    const cancel = () => {
        if (settled) return;
        settled = true;
        wrapper.replaceWith(ellipsisEl);
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') commit();
        else if (e.key === 'Escape') cancel();
    });

    input.addEventListener('blur', commit);
}

/**
 * Scroll to top of archive section
 */
function scrollToTop() {
    const archive = document.querySelector('.archive');
    if (archive) {
        const headerHeight = document.querySelector('.header')?.offsetHeight || 0;
        const filterHeight = document.querySelector('.filter-bar')?.offsetHeight || 0;
        const offset = headerHeight + filterHeight + 20;
        const targetPosition = archive.offsetTop - offset;
        
        window.scrollTo({
            top: targetPosition,
            behavior: 'smooth'
        });
    }
}

/**
 * Setup search bar functionality
 */
function setupSearchBar() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) {
        // Create search bar if it doesn't exist
        createSearchBar();
        return;
    }
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        
        // Debounce search to avoid too many API calls
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            if (query !== currentSearch) {
                currentSearch = query;
                resetAndReload();
            }
        }, 500); // Wait 500ms after user stops typing
    });
    
    // Clear button
    const clearBtn = document.getElementById('clearSearch');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            currentSearch = '';
            clearBtn.style.display = 'none';
            resetAndReload();
        });
    }
    
    // Show/hide clear button
    searchInput.addEventListener('input', (e) => {
        const clearBtn = document.getElementById('clearSearch');
        if (clearBtn) {
            clearBtn.style.display = e.target.value ? 'block' : 'none';
        }
    });
}

/**
 * Create search bar UI element
 */
function createSearchBar() {
    const filterBar = document.querySelector('.filter-bar');
    if (!filterBar) return;
    
    const searchContainer = document.createElement('div');
    searchContainer.className = 'search-container';
    
    const searchWrapper = document.createElement('div');
    searchWrapper.className = 'search-wrapper';
    
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.id = 'searchInput';
    searchInput.className = 'search-input';
    searchInput.placeholder = 'Search papers by title, summary, or journal...';
    searchInput.setAttribute('aria-label', 'Search research papers');
    
    const searchIcon = document.createElement('i');
    searchIcon.className = 'fas fa-search';
    searchIcon.style.cssText = `
        position: absolute;
        left: 15px;
        top: 50%;
        transform: translateY(-50%);
        color: #6b7280;
        pointer-events: none;
    `;
    
    const clearBtn = document.createElement('button');
    clearBtn.id = 'clearSearch';
    clearBtn.className = 'clear-search-btn';
    clearBtn.innerHTML = '<i class="fas fa-times"></i>';
    clearBtn.setAttribute('aria-label', 'Clear search');
    clearBtn.style.display = 'none';
    
    clearBtn.addEventListener('mouseenter', () => {
        clearBtn.style.color = '#ef4444';
    });
    
    clearBtn.addEventListener('mouseleave', () => {
        clearBtn.style.color = '#6b7280';
    });
    
    searchWrapper.appendChild(searchIcon);
    searchWrapper.appendChild(searchInput);
    searchWrapper.appendChild(clearBtn);
    searchContainer.appendChild(searchWrapper);

    const viewToggle = document.createElement('div');
    viewToggle.className = 'view-toggle' + (currentView === 'grid' ? ' grid-active' : '');
    viewToggle.setAttribute('role', 'button');
    viewToggle.setAttribute('tabindex', '0');
    viewToggle.setAttribute('aria-label', `Toggle view (currently ${currentView})`);

    const thumb = document.createElement('span');
    thumb.className = 'view-toggle-thumb';

    const listIcon = document.createElement('span');
    listIcon.className = 'view-toggle-icon';
    listIcon.dataset.view = 'list';
    listIcon.innerHTML = '<i class="fas fa-list" aria-hidden="true"></i>';

    const gridIcon = document.createElement('span');
    gridIcon.className = 'view-toggle-icon';
    gridIcon.dataset.view = 'grid';
    gridIcon.innerHTML = '<i class="fas fa-th" aria-hidden="true"></i>';

    viewToggle.appendChild(thumb);
    viewToggle.appendChild(listIcon);
    viewToggle.appendChild(gridIcon);
    searchContainer.appendChild(viewToggle);

    filterBar.parentNode.insertBefore(searchContainer, filterBar.nextSibling);
    
    // Setup event listeners
    setupSearchBar();
}

/**
 * Reset state and reload from beginning
 */
function resetAndReload() {
    pageCache.clear();
    prefetchInProgress.clear();
    currentPage = 1;
    totalPages = 1;
    isLastPage = false;
    loadPage(1);
}

/**
 * Load a specific page of papers
 * @param {number} pageNumber - Page number to load (1-indexed)
 * @param {boolean} isBackground - Whether this is a background prefetch
 */
async function loadPage(pageNumber, isBackground = false) {
    // Cache hit — restore full state from cached entry
    const cached = pageCache.get(pageNumber);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
        if (!isBackground) {
            currentPage = pageNumber;
            totalPages = cached.pagination.total_pages || totalPages;
            isLastPage = cached.isLastPage;
            renderPageFromCache(cached);
            updatePaginationDisplay();
            updateStatsDisplay();
        }
        return;
    }

    if (isBackground) {
        prefetchInProgress.add(pageNumber);
    } else {
        // Update page state and show skeleton immediately so the UI
        // reflects the navigation intent before the fetch resolves
        currentPage = pageNumber;
        isLoading = true;
        showSkeletonCards(currentPerPage);
        updatePaginationDisplay();
    }

    const myLoadId = ++currentLoadId;

    try {
        const offset = (pageNumber - 1) * currentPerPage;
        const result = await fetchPapersFromServer(currentPerPage, offset);

        // A newer foreground load started while this one was in flight — discard.
        if (!isBackground && myLoadId !== currentLoadId) return;

        const isThisLastPage = !result.pagination.has_next_page;

        pageCache.set(pageNumber, {
            papers: result.papers,
            pagination: result.pagination,
            filters: result.filters,
            timestamp: Date.now(),
            isLastPage: isThisLastPage
        });

        // totalPages is consistent across all pages for the same query,
        // so background prefetches can safely update it.
        // isLastPage is current-page state — only the foreground fetch owns it.
        totalPages = result.pagination.total_pages || 1;

        if (!isBackground) {
            isLoading = false;
            isLastPage = isThisLastPage;
            renderPageFromCache(pageCache.get(pageNumber));
            updatePaginationDisplay();
            updateStatsDisplay();
        }

    } catch (error) {
        console.error('Error loading page:', error);
        if (!isBackground && myLoadId === currentLoadId) {
            isLoading = false;
            showTemporaryNotification('Failed to load page. Please try again.', 'error');
        }
    } finally {
        if (isBackground) {
            prefetchInProgress.delete(pageNumber);
        }
    }
}

/**
 * Render skeleton placeholder cards while a page fetch is in progress
 * @param {number} count - Number of skeleton cards to show
 */
function showSkeletonCards(count) {
    const grid = document.getElementById('archiveGrid');
    if (!grid) return;

    applyViewClass();

    // Always make skeleton visible — previous render may have left opacity at 0.
    grid.style.transition = 'none';
    grid.style.opacity = '1';

    if (currentView === 'list') {
        grid.innerHTML = Array.from({ length: count }, () => `
            <article class="paper-card list-layout skeleton" aria-hidden="true">
                <span class="skeleton-block skeleton-badge"></span>
                <div class="list-body">
                    <div class="skeleton-block skeleton-title"></div>
                    <div class="skeleton-block skeleton-journal" style="margin-top:6px;"></div>
                </div>
                <div class="list-meta">
                    <span class="skeleton-block skeleton-date"></span>
                    <span class="skeleton-block" style="width:80px;height:28px;border-radius:6px;"></span>
                </div>
            </article>
        `).join('');
    } else {
        grid.innerHTML = Array.from({ length: count }, () => `
            <article class="paper-card skeleton" aria-hidden="true">
                <div class="paper-header">
                    <span class="skeleton-block skeleton-badge"></span>
                    <span class="skeleton-block skeleton-date"></span>
                </div>
                <div class="skeleton-block skeleton-title"></div>
                <div class="skeleton-block skeleton-journal"></div>
                <div class="paper-footer">
                    <span class="skeleton-block" style="width:80px;height:26px;border-radius:8px;"></span>
                </div>
            </article>
        `).join('');
    }
}

/**
 * Render papers from cached page data
 */
function renderPageFromCache(cachedPage) {
    const grid = document.getElementById('archiveGrid');
    if (!grid) return;

    applyViewClass();

    const papers = cachedPage.papers;
    
    // Announce change for screen readers
    announceFilterChange(papers.length, currentFilter);

    if (papers.length === 0) {
        let message = 'No papers found.';

        if (currentSearch) {
            message = `No papers found matching "${currentSearch}".`;
        } else if (currentFilter !== 'all') {
            message = `No ${currentFilter} papers found.`;
        }

        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-search" aria-hidden="true"></i>
                <p>${message}</p>
            </div>
        `;
    } else {
        grid.innerHTML = papers.map(paper => createPaperCard(paper)).join('');
    }

    // Content is in the DOM — snap to opacity 0, force a reflow so the
    // browser commits the change, then animate back to 1.  This gives a
    // clean fade-in with no blank-screen gap between hiding the skeleton
    // and revealing the real cards.
    grid.style.transition = 'none';
    grid.style.opacity = '0';
    grid.getBoundingClientRect(); // force reflow
    grid.style.transition = 'opacity 0.2s ease';
    grid.style.opacity = '1';

    window.dispatchEvent(new Event('papersRendered'));
}

/**
 * Fetch papers from the server
 * @param {number} limit - Number of papers to fetch
 * @param {number} offset - Number of papers to skip
 * @returns {Promise<Object>} Server response with papers and pagination metadata
 */
async function fetchPapersFromServer(limit, offset = 0) {
    const params = new URLSearchParams();

    params.append('limit', limit.toString());
    params.append('offset', offset.toString());

    if (currentFilter !== 'all') {
        params.append('topic', currentFilter);
    }

    if (currentSearch) {
        params.append('search', currentSearch);
    }

    params.append('sort', currentSort);

    const url = `${API_BASE_URL}/archive/latest?${params.toString()}`;

    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
}

/**
 * Update stats display
 */
function updateStatsDisplay() {
    let statsDiv = document.getElementById('archiveStats');
    
    if (!statsDiv) {
        const archiveSection = document.querySelector('.archive');
        if (!archiveSection) return;
        
        statsDiv = document.createElement('div');
        statsDiv.id = 'archiveStats';
        statsDiv.style.cssText = `
            text-align: center;
            margin-top: var(--space-md);
            margin-bottom: var(--space-md);
            color: var(--color-text-secondary);
            font-size: 0.9rem;
        `;
        
        const sectionTitle = archiveSection.querySelector('.section-title');
        if (sectionTitle && sectionTitle.nextSibling) {
            archiveSection.insertBefore(statsDiv, sectionTitle.nextSibling);
        }
    }
    
    if (pageCache.has(currentPage)) {
        const cached = pageCache.get(currentPage);
        const papers = cached.papers;
        
        let message = `Page ${currentPage} of ${totalPages}`;

        if (papers.length > 0) {
            message += ` • ${papers.length} ${papers.length === 1 ? 'paper' : 'papers'}`;
        }
        
        if (currentFilter !== 'all' || currentSearch) {
            const filters = [];
            if (currentFilter !== 'all') {
                filters.push(`${currentFilter}`);
            }
            if (currentSearch) {
                filters.push(`"${currentSearch}"`);
            }
            message += ` • ${filters.join(' • ')}`;
        }
        
        statsDiv.textContent = message;
        statsDiv.style.display = 'block';
    } else {
        statsDiv.style.display = 'none';
    }
}

/**
 * Pre-fetch a specific page (called on hover)
 * @param {number} pageNumber - Page number to pre-fetch
 */
function prefetchPage(pageNumber) {
    if (pageNumber < 1 ||
        pageNumber > totalPages ||
        pageCache.has(pageNumber) ||
        prefetchInProgress.has(pageNumber)) {
        return;
    }
    
    console.log(`🔄 Pre-fetching page ${pageNumber} (hover triggered)`);
    loadPage(pageNumber, true); // true = background fetch
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    const subscribeButtons = document.querySelectorAll('.subscribe-btn');
    subscribeButtons.forEach(button => {
        button.addEventListener('click', openModal);
    });
    
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(button => {
        button.addEventListener('click', handleFilterClick);
    });
    
    const closeButton = document.querySelector('.close-btn');
    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
    }
    
    const modalOverlay = document.getElementById('modalOverlay');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', handleBackdropClick);
    }
    
    const form = document.getElementById('subscribeForm');
    if (form) {
        form.addEventListener('submit', handleSubmit);
    }
}

/**
 * Handle filter button clicks
 */
function handleFilterClick(event) {
    const button = event.currentTarget;
    const topic = button.dataset.topic;
    
    // Update active state
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
    });
    
    button.classList.add('active');
    button.setAttribute('aria-pressed', 'true');
    
    // Update filter and reload
    if (topic !== currentFilter) {
        currentFilter = topic;
        resetAndReload();
    }
}

/**
 * Create HTML for a paper card
 */
function createPaperCard(paper) {
    const topicLabel = paper.topic.charAt(0).toUpperCase() + paper.topic.slice(1);
    const badgeColor = topicColors[paper.topic] || topicColors.default;

    if (currentView === 'list') {
        return `
            <article class="paper-card list-layout" aria-labelledby="paper-${paper.topic}-title" data-summary="${escapeHtml(paper.summary)}">
                <span class="topic-badge" style="background: ${badgeColor}" role="text">
                    ${topicLabel.toUpperCase()}
                </span>
                <div class="list-body">
                    <h3 id="paper-${paper.topic}-title" class="paper-title">${escapeHtml(paper.title)}</h3>
                    <span class="journal">${escapeHtml(paper.journal)}</span>
                </div>
                <div class="list-meta">
                    <time class="date" datetime="${paper.date}">${paper.date}</time>
                    <a
                        href="${escapeHtml(paper.url)}"
                        class="read-more"
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="Read full paper: ${escapeHtml(paper.title)} (opens in new tab)"
                    >Read paper</a>
                </div>
            </article>
        `;
    }

    // Grid view (no summary, journal below header)
    return `
        <article class="paper-card" aria-labelledby="paper-${paper.topic}-title" data-summary="${escapeHtml(paper.summary)}">
            <div class="paper-header">
                <span
                    class="topic-badge"
                    style="background: ${badgeColor}"
                    role="text"
                >
                    ${topicLabel.toUpperCase()}
                </span>
                <time class="date" datetime="${paper.date}">${paper.date}</time>
            </div>
            <h3 id="paper-${paper.topic}-title" class="paper-title">${escapeHtml(paper.title)}</h3>
            <span class="journal">${escapeHtml(paper.journal)}</span>
            <div class="paper-footer">
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
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show temporary notification
 */
function showTemporaryNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

/**
 * Announce filter change to screen readers
 */
function announceFilterChange(count, filter) {
    const status = document.getElementById('filter-status');
    if (status) {
        const filterText = filter === 'all' ? 'all topics' : filter;
        status.textContent = `Showing ${count} papers in ${filterText}`;
    }
}

/**
 * Setup topic checkboxes in subscription modal
 */
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

/**
 * Setup floating preview card (Option B)
 * Creates a stylish tooltip-like preview that appears on the opposite side
 * of the screen from the cursor position. The preview follows the cursor
 * vertically as you move within a card, creating a responsive feel.
 */
function setupPreviewCard() {
    // Create simplified preview card element (title, journal, and summary)
    const previewCard = document.createElement('div');
    previewCard.className = 'preview-card';
    previewCard.setAttribute('role', 'tooltip');
    previewCard.setAttribute('aria-hidden', 'true');
    previewCard.innerHTML = `
        <div class="preview-card-header">
            <h3 class="preview-title"></h3>
            <p class="preview-journal"></p>
        </div>
        <p class="preview-summary"></p>
    `;
    document.body.appendChild(previewCard);
    console.log('✅ Preview card created and added to body');
    
    let showTimeout = null;
    let hideTimeout = null;
    let currentSide = null; // Track current side (left or right)
    let lastMoveTime = 0;
    const moveThrottle = 30; // Update position at most every 30ms (more responsive)
    
    /**
     * Update preview card content with paper data
     * Returns true if content is valid, false otherwise
     */
    function updatePreviewContent(paper) {
        // Validate that we have required content
        if (!paper.title || !paper.summary || 
            paper.title.trim() === '' || paper.summary.trim() === '') {
            console.log('❌ Invalid paper content');
            return false;
        }
        
        previewCard.querySelector('.preview-title').textContent = paper.title;
        previewCard.querySelector('.preview-journal').textContent = paper.journal || '';
        previewCard.querySelector('.preview-summary').textContent = paper.summary;
        console.log('✅ Content updated:', paper.title.substring(0, 30) + '...');
        return true;
    }
    
    /**
     * Position preview on opposite side of screen from cursor
     * and align both vertically and horizontally near the cursor position
     */
    function positionPreview(mouseX, mouseY) {
        const viewportCenterX = window.innerWidth / 2;
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;
        const distanceFromCenter = Math.abs(mouseX - viewportCenterX);
        
        // Determine horizontal position (opposite side from cursor)
        const newSide = mouseX < viewportCenterX ? 'right' : 'left';
        
        // Calculate dynamic horizontal offset from cursor
        const horizontalOffset = 48; // ~3rem (48px) away from cursor
        const previewWidth = 380; // preview card width
        const margin = 20; // minimum margin from screen edges
        
        let horizontalPosition;
        
        if (newSide === 'right') {
            // Cursor is on left, show preview on right
            // Position preview to the right of cursor
            horizontalPosition = mouseX + horizontalOffset;
            
            // Ensure we don't go off the right edge
            if (horizontalPosition + previewWidth > viewportWidth - margin) {
                horizontalPosition = viewportWidth - previewWidth - margin;
            }
        } else {
            // Cursor is on right, show preview on left
            // Position preview to the left of cursor
            horizontalPosition = mouseX - horizontalOffset - previewWidth;
            
            // Ensure we don't go off the left edge
            if (horizontalPosition < margin) {
                horizontalPosition = margin;
            }
        }
        
        // Check if side is changing
        const sideChanged = currentSide !== null && currentSide !== newSide;
        
        if (sideChanged) {
            console.log('📍 Side changing - Cursor position:', { 
                mouseX, 
                mouseY, 
                newSide, 
                oldSide: currentSide,
                distanceFromCenter: Math.round(distanceFromCenter),
                horizontalPosition: Math.round(horizontalPosition)
            });
        }
        
        if (sideChanged) {
            // Fade out, change side, then fade in
            previewCard.classList.add('transitioning');
            
            setTimeout(() => {
                // Remove existing position classes
                previewCard.classList.remove('preview-left', 'preview-right');
                
                // Add new position class
                previewCard.classList.add(`preview-${newSide}`);
                currentSide = newSide;
                
                // Set horizontal position (always use left for consistency)
                previewCard.style.left = `${horizontalPosition}px`;
                previewCard.style.right = 'auto';
                
                // Remove transitioning class to fade back in
                previewCard.classList.remove('transitioning');
                console.log('✅ Side transition complete:', newSide, 'at position:', Math.round(horizontalPosition));
            }, 250); // Match transition duration (0.25s)
        } else {
            // Remove existing position classes
            previewCard.classList.remove('preview-left', 'preview-right');
            
            // Add new position class
            previewCard.classList.add(`preview-${newSide}`);
            currentSide = newSide;
            
            // Set horizontal position (always use left for consistency)
            previewCard.style.left = `${horizontalPosition}px`;
            previewCard.style.right = 'auto';
        }
        
        // Calculate vertical position near cursor
        // Center the preview around the cursor Y position
        const previewHeight = previewCard.offsetHeight || 400; // fallback estimate
        let top = mouseY - (previewHeight / 2);
        
        // Add margin from top/bottom edges
        const verticalMargin = 20;
        
        // Ensure preview doesn't go off top of screen
        if (top < verticalMargin) {
            top = verticalMargin;
        }
        
        // Ensure preview doesn't go off bottom of screen
        if (top + previewHeight > viewportHeight - verticalMargin) {
            top = Math.max(verticalMargin, viewportHeight - previewHeight - verticalMargin);
        }
        
        // Apply vertical position
        previewCard.style.top = `${top}px`;
    }
    
    /**
     * Show preview card with proper animation timing
     */
    function showPreview() {
        clearTimeout(showTimeout);
        clearTimeout(hideTimeout);
        
        // Small delay to ensure smooth animation
        showTimeout = setTimeout(() => {
            previewCard.classList.add('active');
            previewCard.setAttribute('aria-hidden', 'false');
            console.log('✅ Preview shown, classes:', previewCard.className);
            console.log('📊 Computed opacity:', getComputedStyle(previewCard).opacity);
        }, 30);
    }
    
    /**
     * Hide preview card
     */
    function hidePreview() {
        clearTimeout(showTimeout);
        clearTimeout(hideTimeout);
        
        // Add slight delay to prevent flickering
        hideTimeout = setTimeout(() => {
            previewCard.classList.remove('active');
            previewCard.setAttribute('aria-hidden', 'true');
            currentSide = null; // Reset side tracking
            console.log('✅ Preview hidden');
        }, 50);
    }
    
    /**
     * Attach listeners to all paper cards
     */
    function attachCardListeners() {
        const cards = document.querySelectorAll('.paper-card');
        console.log(`🔗 Attaching listeners to ${cards.length} cards`);
        
        cards.forEach((card, index) => {
            // Remove existing listeners if any (to avoid duplicates)
            card.removeEventListener('mouseenter', card._previewEnterHandler);
            card.removeEventListener('mouseleave', card._previewLeaveHandler);
            card.removeEventListener('mousemove', card._previewMoveHandler);
            
            // Create handlers
            const enterHandler = (e) => {
                console.log(`🖱️ Mouse entered card ${index} at position (${e.clientX}, ${e.clientY})`);
                
                // Get mouse position
                const mouseX = e.clientX;
                const mouseY = e.clientY;
                
                // Extract paper data from card
                const title = card.querySelector('.paper-title')?.textContent;
                const summary = card.dataset.summary;
                const journal = card.querySelector('.journal')?.textContent;
                
                // Only show preview if content is valid
                if (title && summary) {
                    const paper = { title, summary, journal };
                    const isValid = updatePreviewContent(paper);
                    
                    if (isValid) {
                        positionPreview(mouseX, mouseY);
                        showPreview();
                    }
                }
            };
            
            const leaveHandler = () => {
                console.log(`🖱️ Mouse left card ${index}`);
                hidePreview();
            };
            
            const moveHandler = (e) => {
                // Throttle mousemove updates for performance
                const now = Date.now();
                if (now - lastMoveTime < moveThrottle) {
                    return;
                }
                lastMoveTime = now;
                
                // Update preview position as mouse moves within card
                if (previewCard.classList.contains('active')) {
                    const mouseX = e.clientX;
                    const mouseY = e.clientY;
                    console.log(`🎯 Cursor tracking: (${mouseX}, ${mouseY})`);
                    positionPreview(mouseX, mouseY);
                }
            };
            
            // Store handlers on element for cleanup
            card._previewEnterHandler = enterHandler;
            card._previewLeaveHandler = leaveHandler;
            card._previewMoveHandler = moveHandler;
            
            // Attach listeners
            card.addEventListener('mouseenter', enterHandler);
            card.addEventListener('mouseleave', leaveHandler);
            card.addEventListener('mousemove', moveHandler);
        });
    }
    
    // Initial setup - delay to ensure cards are rendered
    setTimeout(() => {
        attachCardListeners();
    }, 500);
    
    // Reattach when cards are re-rendered
    const archiveGrid = document.getElementById('archiveGrid');
    if (archiveGrid) {
        const observer = new MutationObserver(() => {
            setTimeout(() => {
                attachCardListeners();
            }, 100);
        });
        
        observer.observe(archiveGrid, { childList: true });
    }
    
    // Also reattach after render (backup method)
    window.addEventListener('papersRendered', () => {
        setTimeout(() => {
            attachCardListeners();
        }, 100);
    });
}

/**
 * Apply the current view class to the archive grid
 */
function applyViewClass() {
    const grid = document.getElementById('archiveGrid');
    if (!grid) return;
    grid.classList.toggle('list-view', currentView === 'list');
    grid.classList.toggle('grid-view', currentView === 'grid');
}

/**
 * Setup view toggle (List / Grid) single paddle
 */
function setupViewToggle() {
    const toggle = document.querySelector('.view-toggle');
    if (!toggle) return;

    function activateToggle() {
        currentView = currentView === 'list' ? 'grid' : 'list';
        toggle.classList.toggle('grid-active', currentView === 'grid');
        toggle.setAttribute('aria-label', `Toggle view (currently ${currentView})`);
        applyViewClass();
        const cached = pageCache.get(currentPage);
        if (cached) renderPageFromCache(cached);
    }

    toggle.addEventListener('click', activateToggle);
    toggle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            activateToggle();
        }
    });
}

/**
 * Setup scroll effects for header
 */
function setupScrollEffects() {
    const header = document.querySelector('.header');
    const filterBar = document.querySelector('.filter-bar');

    if (!header || !filterBar) return;

    function syncHeaderHeight() {
        document.documentElement.style.setProperty('--header-height', `${header.offsetHeight}px`);
    }
    syncHeaderHeight();
    window.addEventListener('resize', syncHeaderHeight);

    let lastScroll = 0;
    const scrollThreshold = 50;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;

        if (currentScroll > scrollThreshold) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }

        lastScroll = currentScroll;
    });
}

/**
 * Setup keyboard navigation
 */
function setupKeyboardNav() {
    document.addEventListener('keydown', (event) => {
        const modalOverlay = document.getElementById('modalOverlay');
        const isModalOpen = modalOverlay && modalOverlay.classList.contains('active');
        
        if (event.key === 'Escape' && isModalOpen) {
            closeModal();
        }
        
        if (event.key === 'Tab' && isModalOpen) {
            trapFocus(event);
        }
    });
}

/**
 * Trap focus within modal
 */
function trapFocus(event) {
    const modal = document.querySelector('.modal');
    if (!modal) return;
    
    if (focusableElements.length === 0) {
        focusableElements = getFocusableElements(modal);
    }
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
    }
}

/**
 * Open subscription modal
 */
function openModal() {
    const modalOverlay = document.getElementById('modalOverlay');
    if (!modalOverlay) return;
    
    lastFocusedElement = document.activeElement;
    
    modalOverlay.classList.add('active');
    modalOverlay.setAttribute('aria-hidden', 'false');
    
    document.body.style.overflow = 'hidden';
    
    const modal = modalOverlay.querySelector('.modal');
    if (modal) {
        focusableElements = getFocusableElements(modal);
        
        setTimeout(() => {
            const firstFocusable = focusableElements[0];
            if (firstFocusable) {
                firstFocusable.focus();
            }
        }, 100);
    }
}

/**
 * Close subscription modal
 */
function closeModal() {
    const modalOverlay = document.getElementById('modalOverlay');
    if (!modalOverlay) return;
    
    modalOverlay.classList.remove('active');
    modalOverlay.setAttribute('aria-hidden', 'true');
    
    document.body.style.overflow = '';
    
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
    }
    
    setTimeout(() => {
        const form = document.getElementById('subscribeForm');
        if (form) {
            form.reset();
        }
        
        clearFormErrors();
        
        const messageDiv = document.getElementById('message');
        if (messageDiv) {
            messageDiv.innerHTML = '';
        }
        
        setupCheckboxes();
    }, 300);
}

/**
 * Handle backdrop click to close modal
 */
function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
        closeModal();
    }
}

/**
 * Get focusable elements within container
 */
function getFocusableElements(container) {
    const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const elements = container.querySelectorAll(selector);
    
    return Array.from(elements).filter(el => 
        !el.hasAttribute('disabled') && 
        !el.hasAttribute('hidden') &&
        el.tabIndex !== -1
    );
}

/**
 * Handle subscription form submit
 */
async function handleSubmit(event) {
    event.preventDefault();
    
    const form = event.target;
    const email = form.email.value.trim();
    const topicCheckboxes = form.querySelectorAll('input[name="topics"]:checked');
    const topics = Array.from(topicCheckboxes).map(input => input.value);
    
    const messageDiv = document.getElementById('message');
    const submitBtn = document.getElementById('submitBtn');
    
    clearFormErrors();
    if (messageDiv) {
        messageDiv.innerHTML = '';
    }
    
    let hasError = false;
    
    if (!email || !isValidEmail(email)) {
        showFieldError('email', 'Please enter a valid email address.');
        hasError = true;
    }
    
    if (topics.length === 0) {
        showFieldError('topics', 'Please select at least one topic.');
        
        const checkboxContainer = document.querySelector('.topic-checkboxes');
        if (checkboxContainer) {
            checkboxContainer.style.animation = 'none';
            void checkboxContainer.offsetWidth;
            checkboxContainer.style.animation = 'shake 0.5s ease';
        }
        
        hasError = true;
    }
    
    if (hasError) {
        const firstError = document.querySelector('.form-input.error, .topic-checkboxes');
        if (firstError) {
            firstError.focus();
        }
        return;
    }
    
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Subscribing...';
        submitBtn.classList.add('loading');
        submitBtn.setAttribute('aria-busy', 'true');
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/subscribe`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, topics })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="message success" role="status"><i class="fas fa-check-circle"></i> Success! Check your email to confirm your subscription.</div>';
            }
            
            form.reset();
            setupCheckboxes();
            
            setTimeout(() => {
                closeModal();
            }, 3000);
        } else {
            const errorMessage = data.error || 'Subscription failed. Please try again.';
            if (messageDiv) {
                messageDiv.innerHTML = `<div class="message error" role="alert"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(errorMessage)}</div>`;
            }
        }
    } catch (error) {
        console.error('Subscription error:', error);
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="message error" role="alert"><i class="fas fa-exclamation-circle"></i> Network error. Please check your connection and try again.</div>';
        }
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Subscribe';
            submitBtn.classList.remove('loading');
            submitBtn.removeAttribute('aria-busy');
        }
    }
}

/**
 * Validate email format
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Show field error message
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
 * Clear all form errors
 */
function clearFormErrors() {
    const emailInput = document.getElementById('email');
    const emailError = document.getElementById('email-error');
    
    if (emailInput) {
        emailInput.classList.remove('error');
        emailInput.removeAttribute('aria-invalid');
    }
    
    if (emailError) {
        emailError.textContent = '';
    }
    
    const topicsError = document.getElementById('topics-error');
    if (topicsError) {
        topicsError.textContent = '';
    }
}

// Respect user's motion preferences
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.style.setProperty('--transition-fast', '0.01ms');
    document.documentElement.style.setProperty('--transition-normal', '0.01ms');
    document.documentElement.style.setProperty('--transition-slow', '0.01ms');
}