// Hubfeed Agent Web UI JavaScript - Refactored with State Machine

// ====== Constants ======
const QR_STATES = {
    IDLE: 'idle',
    GENERATING: 'generating',
    READY: 'ready',
    AUTHENTICATING: 'authenticating',
    SUCCESS: 'success',
    ERROR: 'error'
};

// ====== State Management ======
const state = {
    token: localStorage.getItem('auth_token'),
    username: localStorage.getItem('username'),
    currentTab: 'setup',
    phoneCodeHash: null
};

// QR Authentication State (separate for clarity)
const qrAuthState = {
    state: QR_STATES.IDLE,
    avatarId: null,
    expiresAt: null,
    pollingInterval: null,
    expirationTimer: null,
    countdownInterval: null,
    errorMessage: null
};

// ====== API Client ======
class ApiClient {
    constructor() {
        this.baseUrl = '/api';
    }

    async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (state.token && !endpoint.includes('/auth/login')) {
            headers['Authorization'] = `Bearer ${state.token}`;
        }

        const config = {
            ...options,
            headers
        };

        const response = await fetch(`${this.baseUrl}${endpoint}`, config);

        if (response.status === 401) {
            logout();
            throw new Error('Unauthorized');
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'API request failed');
        }

        return data;
    }

    // Auth
    async login(username, password) {
        return this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
    }

    // Config
    async getConfig() {
        return this.request('/config');
    }

    async updateConfig(token) {
        return this.request('/config', {
            method: 'POST',
            body: JSON.stringify({ token })
        });
    }

    // Avatars
    async getAvatars() {
        return this.request('/avatars');
    }

    async deleteAvatar(avatarId) {
        return this.request(`/avatars/${avatarId}`, { method: 'DELETE' });
    }

    // Telegram Auth
    async startQRAuth(avatarId) {
        return this.request('/avatars/telegram/qr/start', {
            method: 'POST',
            body: JSON.stringify({ avatar_id: avatarId })
        });
    }

    async checkQRStatus(avatarId, timeout = 30) {
        return this.request(`/avatars/telegram/qr/status/${avatarId}?timeout=${timeout}`);
    }

    async cancelQRAuth(avatarId) {
        return this.request(`/avatars/telegram/qr/cancel/${avatarId}`, { method: 'POST' });
    }

    async startPhoneAuth(avatarId, phone) {
        return this.request('/avatars/telegram/phone/start', {
            method: 'POST',
            body: JSON.stringify({ avatar_id: avatarId, phone })
        });
    }

    async completePhoneAuth(avatarId, phone, code, phoneCodeHash, password = null) {
        return this.request('/avatars/telegram/phone/complete', {
            method: 'POST',
            body: JSON.stringify({
                avatar_id: avatarId,
                phone,
                code,
                phone_code_hash: phoneCodeHash,
                password
            })
        });
    }

    // Blacklist
    async getBlacklist() {
        return this.request('/blacklist');
    }

    async updateBlacklist(blacklist) {
        return this.request('/blacklist', {
            method: 'PUT',
            body: JSON.stringify({ blacklist })
        });
    }

    // History
    async getHistory(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/history?${query}`);
    }

    // Status
    async getStatus() {
        return this.request('/status');
    }

    // Control
    async startAgent() {
        return this.request('/control/start', { method: 'POST' });
    }

    async stopAgent() {
        return this.request('/control/stop', { method: 'POST' });
    }
}

const api = new ApiClient();

// ====== UI Helpers ======
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(pageId);
    page.classList.add('active');
    page.style.animation = 'fadeIn 0.4s ease-out';
}

function showTab(tabName) {
    state.currentTab = tabName;

    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[data-tab="${tabName}"]`).classList.add('active');

    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.remove('active');
        c.style.animation = 'none';
    });

    const tabContent = document.getElementById(`${tabName}-tab`);
    tabContent.classList.add('active');
    // Trigger fade-in animation
    tabContent.style.animation = 'none';
    tabContent.offsetHeight; // Force reflow
    tabContent.style.animation = 'fadeInUp 0.3s ease-out';

    // Load data for specific tabs
    if (tabName === 'setup') loadConfig();
    if (tabName === 'avatars') loadAvatars();
    if (tabName === 'blacklist') loadBlacklist();
    if (tabName === 'history') loadHistory();
    if (tabName === 'status') loadStatus();
}

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    setTimeout(() => el.textContent = '', 5000);
}

function showSuccess(elementId, message) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    setTimeout(() => el.textContent = '', 5000);
}

function setLoading(button, loading) {
    if (loading) {
        button.classList.add('loading');
        button.disabled = true;
    } else {
        button.classList.remove('loading');
        button.disabled = false;
    }
}

// ====== Authentication ======
async function handleLogin(e) {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const submitBtn = e.target.querySelector('button[type="submit"]');
    
    setLoading(submitBtn, true);
    showError('login-error', '');
    
    try {
        const response = await api.login(username, password);
        
        state.token = response.token;
        state.username = response.username;
        
        localStorage.setItem('auth_token', response.token);
        localStorage.setItem('username', response.username);
        
        showPage('dashboard-page');
        document.getElementById('username-display').textContent = response.username;
        startHeaderStatusPolling();
        loadConfig();
    } catch (error) {
        showError('login-error', error.message);
    } finally {
        setLoading(submitBtn, false);
    }
}

function logout() {
    stopHeaderStatusPolling();
    state.token = null;
    state.username = null;
    localStorage.removeItem('auth_token');
    localStorage.removeItem('username');
    showPage('login-page');
}

// ====== Configuration ======
async function loadConfig() {
    try {
        const data = await api.getConfig();

        document.getElementById('agent-token').value = data.config.token || '';
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

async function handleConfigSubmit(e) {
    e.preventDefault();

    const token = document.getElementById('agent-token').value;
    const submitBtn = e.target.querySelector('button[type="submit"]');

    setLoading(submitBtn, true);
    showError('config-error', '');
    showSuccess('config-success', '');

    try {
        await api.updateConfig(token);
        showSuccess('config-success', 'Configuration saved successfully');
    } catch (error) {
        showError('config-error', error.message);
    } finally {
        setLoading(submitBtn, false);
    }
}

async function handleStartAgent() {
    const btn = document.getElementById('start-agent-btn');
    setLoading(btn, true);

    try {
        const response = await api.startAgent();
        document.getElementById('control-message').textContent = response.message;
        setTimeout(() => { loadStatus(); updateHeaderStatus(); }, 1000);
    } catch (error) {
        document.getElementById('control-message').textContent = error.message;
    } finally {
        setLoading(btn, false);
    }
}

async function handleStopAgent() {
    const btn = document.getElementById('stop-agent-btn');
    setLoading(btn, true);

    try {
        const response = await api.stopAgent();
        document.getElementById('control-message').textContent = response.message;
        setTimeout(() => { loadStatus(); updateHeaderStatus(); }, 1000);
    } catch (error) {
        document.getElementById('control-message').textContent = error.message;
    } finally {
        setLoading(btn, false);
    }
}

// ====== Avatars ======
async function loadAvatars() {
    const container = document.getElementById('avatars-list');
    container.innerHTML = '<div class="loading">Loading avatars...</div>';
    
    try {
        const data = await api.getAvatars();
        
        if (data.avatars.length === 0) {
            container.innerHTML = '<p class="help-text">No avatars configured. Click \"+ Add Avatar\" to get started.</p>';
            return;
        }
        
        container.innerHTML = data.avatars.map(avatar => `
            <div class="avatar-item">
                <div class="avatar-info">
                    <h3>
                        ${avatar.name || avatar.id}
                        <span class="avatar-status ${avatar.status}">${avatar.status}</span>
                    </h3>
                    <div class="avatar-meta">
                        ${avatar.platform} • ${avatar.phone || 'No phone'}
                    </div>
                </div>
                <div class="avatar-actions">
                    <button class="btn btn-secondary btn-sm" onclick="openAvatarSettings('${avatar.id}')">⚙️ Configure</button>
                    <button class="btn btn-destructive btn-sm" onclick="deleteAvatar('${avatar.id}')">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<p class="error-message">${error.message}</p>`;
    }
}

async function deleteAvatar(avatarId) {
    if (!confirm('Are you sure you want to delete this avatar?')) return;
    
    try {
        await api.deleteAvatar(avatarId);
        loadAvatars();
    } catch (error) {
        alert('Failed to delete avatar: ' + error.message);
    }
}

function openAddAvatarModal() {
    document.body.style.overflow = 'hidden';
    document.getElementById('add-avatar-modal').classList.add('active');
    
    // Auto-start QR auth if QR method is active
    setTimeout(() => {
        const qrAuthActive = document.getElementById('qr-auth').classList.contains('active');
        if (qrAuthActive) {
            autoStartQRAuth().catch(error => {
                console.error('Auto-start QR auth failed:', error);
                showError('avatar-error', 'Failed to generate QR code. Please try again.');
            });
        }
    }, 100);
}

function closeAddAvatarModal() {
    document.body.style.overflow = '';
    document.getElementById('add-avatar-modal').classList.remove('active');
    cancelQRAuthFlow();
    resetAvatarModal();
}

function resetAvatarModal() {
    document.getElementById('qr-avatar-id').value = '';
    document.getElementById('phone-avatar-id').value = '';
    document.getElementById('phone-number').value = '';
    document.getElementById('phone-code').value = '';
    document.getElementById('phone-password').value = '';
    document.getElementById('phone-code-section').style.display = 'none';
    showError('avatar-error', '');
    showSuccess('avatar-success', '');
    updateQRDisplay(QR_STATES.IDLE);
}

function switchAuthMethod(method) {
    // Cancel any ongoing QR auth
    if (method !== 'qr') {
        cancelQRAuthFlow();
    }
    
    document.querySelectorAll('.auth-method-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.method === method);
    });
    
    document.querySelectorAll('.auth-method').forEach(div => {
        div.classList.toggle('active', div.id === `${method}-auth`);
    });
    
    // Auto-start QR auth when switching to QR method
    if (method === 'qr') {
        setTimeout(() => {
            autoStartQRAuth().catch(error => {
                console.error('Auto-start QR auth failed:', error);
                showError('avatar-error', 'Failed to generate QR code. Please try again.');
            });
        }, 100);
    }
}

// ====== QR Authentication State Machine ======

function transitionQRState(newState, data = {}) {
    console.log(`QR State: ${qrAuthState.state} → ${newState}`);
    
    const oldState = qrAuthState.state;
    qrAuthState.state = newState;
    
    // Handle state-specific cleanup
    if (oldState === QR_STATES.READY && newState !== QR_STATES.READY) {
        // Leaving READY state - stop all timers
        clearTimeout(qrAuthState.pollingInterval);
        clearTimeout(qrAuthState.expirationTimer);
        clearInterval(qrAuthState.countdownInterval);
        qrAuthState.pollingInterval = null;
        qrAuthState.expirationTimer = null;
        qrAuthState.countdownInterval = null;
    }
    
    // Update state data
    if (data.avatarId !== undefined) qrAuthState.avatarId = data.avatarId;
    if (data.expiresAt !== undefined) qrAuthState.expiresAt = data.expiresAt;
    if (data.errorMessage !== undefined) qrAuthState.errorMessage = data.errorMessage;
    
    // Update UI
    updateQRDisplay(newState, data);
}

function canPerformQROperation() {
    return qrAuthState.state === QR_STATES.IDLE || 
           qrAuthState.state === QR_STATES.ERROR;
}

function cleanupQRAuth() {
    console.log('Cleaning up QR auth');
    
    // Clear all timers
    clearTimeout(qrAuthState.pollingInterval);
    clearTimeout(qrAuthState.expirationTimer);
    clearInterval(qrAuthState.countdownInterval);
    qrAuthState.pollingInterval = null;
    qrAuthState.expirationTimer = null;
    qrAuthState.countdownInterval = null;
    
    // Cancel on backend if we have an avatar ID
    if (qrAuthState.avatarId && qrAuthState.state !== QR_STATES.SUCCESS) {
        api.cancelQRAuth(qrAuthState.avatarId).catch(error => {
            console.error('Failed to cancel QR auth on backend:', error);
        });
    }
}

function updateQRDisplay(state, data = {}) {
    const display = document.getElementById('qr-code-display');
    const startBtn = document.getElementById('start-qr-auth-btn');
    const cancelBtn = document.getElementById('cancel-qr-auth-btn');
    
    switch (state) {
        case QR_STATES.IDLE:
            display.innerHTML = `
                <div class="qr-state-message">
                    <p class="help-text">Click "Generate QR Code" to begin authentication</p>
                </div>
            `;
            startBtn.style.display = 'block';
            cancelBtn.style.display = 'none';
            setLoading(startBtn, false);
            break;
            
        case QR_STATES.GENERATING:
            display.innerHTML = `
                <div class="qr-state-message">
                    <div class="spinner"></div>
                    <p>Generating QR code...</p>
                </div>
            `;
            startBtn.style.display = 'none';
            cancelBtn.style.display = 'block';
            setLoading(cancelBtn, false);
            break;
            
        case QR_STATES.READY:
            if (data.qrCodeImage) {
                display.innerHTML = `
                    <div class="qr-code-wrapper">
                        <img src="${data.qrCodeImage}" alt="QR Code" class="qr-code-image">
                        <p class="qr-code-hint">Scan this QR code with your Telegram app</p>
                        <p class="qr-expires-in">Expires in: <span id="qr-countdown">--</span> seconds</p>
                    </div>
                `;
            }
            startBtn.style.display = 'none';
            cancelBtn.style.display = 'block';
            setLoading(cancelBtn, false);
            break;
            
        case QR_STATES.AUTHENTICATING:
            display.innerHTML = `
                <div class="qr-state-message">
                    <div class="spinner"></div>
                    <p>Finalizing authentication...</p>
                </div>
            `;
            startBtn.style.display = 'none';
            cancelBtn.style.display = 'block';
            setLoading(cancelBtn, true); // Disable cancel during auth
            break;
            
        case QR_STATES.SUCCESS:
            display.innerHTML = `
                <div class="qr-state-message qr-success">
                    <div class="success-icon">✓</div>
                    <p>Successfully authenticated!</p>
                </div>
            `;
            startBtn.style.display = 'none';
            cancelBtn.style.display = 'none';
            break;
            
        case QR_STATES.ERROR:
            display.innerHTML = `
                <div class="qr-state-message qr-error">
                    <p class="error-message">${qrAuthState.errorMessage || 'An error occurred'}</p>
                    <button class="btn btn-primary btn-sm" onclick="retryQRAuth()">Try Again</button>
                </div>
            `;
            startBtn.style.display = 'none';
            cancelBtn.style.display = 'block';
            setLoading(cancelBtn, false);
            break;
    }
}

function startCountdownTimer() {
    // Clear any existing countdown
    if (qrAuthState.countdownInterval) {
        clearInterval(qrAuthState.countdownInterval);
    }
    
    if (!qrAuthState.expiresAt) return;
    
    function updateCountdown() {
        const now = new Date();
        const remaining = Math.max(0, Math.floor((qrAuthState.expiresAt - now) / 1000));
        
        const countdownEl = document.getElementById('qr-countdown');
        if (countdownEl) {
            countdownEl.textContent = remaining;
        }
        
        if (remaining <= 0) {
            clearInterval(qrAuthState.countdownInterval);
            qrAuthState.countdownInterval = null;
        }
    }
    
    updateCountdown(); // Immediate update
    qrAuthState.countdownInterval = setInterval(updateCountdown, 1000);
}

async function autoStartQRAuth() {
    if (!canPerformQROperation()) {
        console.log('Cannot start QR auth - operation already in progress');
        return;
    }
    
    let avatarId = document.getElementById('qr-avatar-id').value.trim();
    if (!avatarId) {
        avatarId = `telegram-${Date.now()}`;
        document.getElementById('qr-avatar-id').value = avatarId;
    }
    
    await startQRAuthFlow(avatarId);
}

async function handleStartQRAuth() {
    const avatarId = document.getElementById('qr-avatar-id').value.trim();
    
    if (!avatarId) {
        showError('avatar-error', 'Please enter an avatar name');
        return;
    }
    
    if (!canPerformQROperation()) {
        showError('avatar-error', 'QR authentication already in progress');
        return;
    }
    
    await startQRAuthFlow(avatarId);
}

async function startQRAuthFlow(avatarId) {
    console.log(`Starting QR auth flow for ${avatarId}`);
    
    transitionQRState(QR_STATES.GENERATING, { avatarId });
    showError('avatar-error', '');
    
    try {
        const response = await api.startQRAuth(avatarId);
        
        // Validate state hasn't changed during API call
        if (qrAuthState.state !== QR_STATES.GENERATING || qrAuthState.avatarId !== avatarId) {
            console.log('State changed during QR generation, aborting');
            return;
        }
        
        const expiresAt = response.expires_at ? new Date(response.expires_at) : null;
        
        transitionQRState(QR_STATES.READY, {
            qrCodeImage: response.qr_code_image,
            expiresAt
        });
        
        // Start countdown timer
        if (expiresAt) {
            startCountdownTimer();
            scheduleQRRegeneration(avatarId, expiresAt);
        }
        
        // Start polling for QR scan
        pollQRStatus(avatarId);
        
    } catch (error) {
        console.error('Failed to start QR auth:', error);
        transitionQRState(QR_STATES.ERROR, {
            errorMessage: error.message
        });
        showError('avatar-error', error.message);
    }
}

async function pollQRStatus(avatarId) {
    // Validate state before polling
    if (qrAuthState.state !== QR_STATES.READY || qrAuthState.avatarId !== avatarId) {
        console.log('Polling stopped - state changed or avatar mismatch');
        return;
    }
    
    // Calculate smart timeout based on expiration
    let timeout = 10;
    if (qrAuthState.expiresAt) {
        const now = new Date();
        const remainingMs = qrAuthState.expiresAt - now;
        const remainingSeconds = Math.floor(remainingMs / 1000);
        
        // If expiring very soon, let the expiration timer handle regeneration
        if (remainingSeconds < 5) {
            console.log('QR code expiring very soon, waiting for expiration timer');
            timeout = Math.max(1, remainingSeconds);
        } else {
            timeout = Math.max(5, Math.min(120, remainingSeconds));
        }
    }
    
    console.log(`Polling QR status with ${timeout}s timeout`);
    
    try {
        const response = await api.checkQRStatus(avatarId, timeout);
        
        // Validate state hasn't changed during API call
        if (qrAuthState.state !== QR_STATES.READY || qrAuthState.avatarId !== avatarId) {
            console.log('State changed during polling, stopping');
            return;
        }
        
        if (response.status === 'authenticated') {
            console.log('QR code scanned successfully!');
            
            // Immediate transition to prevent any further operations
            transitionQRState(QR_STATES.AUTHENTICATING);
            
            // Clear timers but DON'T call backend cancel (session is already complete)
            clearTimeout(qrAuthState.pollingInterval);
            clearTimeout(qrAuthState.expirationTimer);
            clearInterval(qrAuthState.countdownInterval);
            qrAuthState.pollingInterval = null;
            qrAuthState.expirationTimer = null;
            qrAuthState.countdownInterval = null;
            
            // Show success
            transitionQRState(QR_STATES.SUCCESS);
            showSuccess('avatar-success', 'Successfully authenticated!');
            
            // Close modal and reload avatars after delay
            setTimeout(() => {
                closeAddAvatarModal();
                loadAvatars();
            }, 2000);
            
        } else if (response.status === 'timeout') {
            console.log('QR status check timed out, regenerating');
            // Backend timed out waiting for scan - regenerate if state allows
            if (qrAuthState.state === QR_STATES.READY && qrAuthState.avatarId === avatarId) {
                await regenerateQRCode(avatarId);
            }
        } else {
            // Continue polling with a short delay
            qrAuthState.pollingInterval = setTimeout(() => {
                pollQRStatus(avatarId);
            }, 1000);
        }
        
    } catch (error) {
        console.error('QR status check error:', error);
        
        // Only transition to error if still in READY state
        if (qrAuthState.state === QR_STATES.READY) {
            transitionQRState(QR_STATES.ERROR, {
                errorMessage: `Connection error: ${error.message}`
            });
            showError('avatar-error', error.message);
        }
    }
}

function scheduleQRRegeneration(avatarId, expiresAt) {
    // Clear any existing expiration timer
    if (qrAuthState.expirationTimer) {
        clearTimeout(qrAuthState.expirationTimer);
        qrAuthState.expirationTimer = null;
    }
    
    if (!expiresAt) return;
    
    const now = new Date();
    const expiresIn = expiresAt - now;
    
    console.log(`QR code expires in ${Math.floor(expiresIn / 1000)} seconds`);
    
    // If already expired or expiring very soon, regenerate immediately
    if (expiresIn < 5000) {
        if (qrAuthState.state === QR_STATES.READY && qrAuthState.avatarId === avatarId) {
            console.log('QR code already expired, regenerating now');
            regenerateQRCode(avatarId);
        }
        return;
    }
    
    // Regenerate 10 seconds before expiration
    const regenerateIn = Math.max(0, expiresIn - 10000);
    
    console.log(`Scheduling regeneration in ${Math.floor(regenerateIn / 1000)} seconds`);
    
    qrAuthState.expirationTimer = setTimeout(async () => {
        console.log('Expiration timer fired');
        
        // Double-check state before regenerating
        if (qrAuthState.state === QR_STATES.READY && qrAuthState.avatarId === avatarId) {
            console.log('Auto-regenerating QR code before expiration');
            await regenerateQRCode(avatarId);
        } else {
            console.log('Skipping regeneration - state or avatar changed');
        }
    }, regenerateIn);
}

async function regenerateQRCode(avatarId) {
    // Only regenerate if in READY state
    if (qrAuthState.state !== QR_STATES.READY || qrAuthState.avatarId !== avatarId) {
        console.log('Cannot regenerate - not in READY state or avatar mismatch');
        return;
    }
    
    console.log('Regenerating QR code...');
    
    // Cancel current session on backend
    try {
        await api.cancelQRAuth(avatarId);
    } catch (error) {
        console.error('Error canceling old QR auth:', error);
    }
    
    // Clear polling timer (expiration timer will be cleared by state transition)
    if (qrAuthState.pollingInterval) {
        clearTimeout(qrAuthState.pollingInterval);
        qrAuthState.pollingInterval = null;
    }
    
    // Start new QR auth flow
    await startQRAuthFlow(avatarId);
}

function retryQRAuth() {
    const avatarId = qrAuthState.avatarId || document.getElementById('qr-avatar-id').value.trim();
    if (!avatarId) {
        showError('avatar-error', 'Please enter an avatar name');
        return;
    }
    
    transitionQRState(QR_STATES.IDLE);
    startQRAuthFlow(avatarId);
}

function cancelQRAuthFlow() {
    if (qrAuthState.state === QR_STATES.IDLE) {
        return; // Nothing to cancel
    }
    
    console.log('Canceling QR auth flow');
    
    cleanupQRAuth();
    transitionQRState(QR_STATES.IDLE, {
        avatarId: null,
        expiresAt: null,
        errorMessage: null
    });
}

async function handleCancelQRAuth() {
    cancelQRAuthFlow();
    resetAvatarModal();
}

// ====== Phone Authentication ======

async function handleStartPhoneAuth() {
    const avatarId = document.getElementById('phone-avatar-id').value.trim();
    const phone = document.getElementById('phone-number').value.trim();
    
    if (!avatarId || !phone) {
        showError('avatar-error', 'Please enter avatar name and phone number');
        return;
    }
    
    const btn = document.getElementById('start-phone-auth-btn');
    setLoading(btn, true);
    showError('avatar-error', '');
    
    try {
        const response = await api.startPhoneAuth(avatarId, phone);
        
        state.phoneCodeHash = response.phone_code_hash;
        document.getElementById('phone-code-section').style.display = 'block';
        showSuccess('avatar-success', 'Code sent! Check your Telegram app.');
    } catch (error) {
        showError('avatar-error', error.message);
    } finally {
        setLoading(btn, false);
    }
}

async function handleCompletePhoneAuth() {
    const avatarId = document.getElementById('phone-avatar-id').value.trim();
    const phone = document.getElementById('phone-number').value.trim();
    const code = document.getElementById('phone-code').value.trim();
    const password = document.getElementById('phone-password').value.trim() || null;
    
    if (!code) {
        showError('avatar-error', 'Please enter the verification code');
        return;
    }
    
    const btn = document.getElementById('complete-phone-auth-btn');
    setLoading(btn, true);
    showError('avatar-error', '');
    
    try {
        await api.completePhoneAuth(avatarId, phone, code, state.phoneCodeHash, password);
        
        showSuccess('avatar-success', 'Successfully authenticated!');
        setTimeout(() => {
            closeAddAvatarModal();
            loadAvatars();
        }, 2000);
    } catch (error) {
        showError('avatar-error', error.message);
    } finally {
        setLoading(btn, false);
    }
}

// ====== Blacklist ======
async function loadBlacklist() {
    try {
        const data = await api.getBlacklist();
        const keywords = data.blacklist.keywords || [];
        document.getElementById('blacklist-keywords').value = keywords.join('\n');
    } catch (error) {
        console.error('Failed to load blacklist:', error);
    }
}

async function handleSaveBlacklist() {
    const keywords = document.getElementById('blacklist-keywords').value
        .split('\n')
        .map(k => k.trim())
        .filter(k => k.length > 0);
    
    const btn = document.getElementById('save-blacklist-btn');
    setLoading(btn, true);
    showError('blacklist-error', '');
    showSuccess('blacklist-success', '');
    
    try {
        await api.updateBlacklist({ keywords });
        showSuccess('blacklist-success', 'Blacklist saved successfully');
    } catch (error) {
        showError('blacklist-error', error.message);
    } finally {
        setLoading(btn, false);
    }
}

// ====== History ======

// History state management
const historyState = {
    allEvents: [],
    filteredEvents: [],
    searchQuery: '',
    eventTypeFilter: 'all',
    showSuccess: true,
    showFailed: true
};

async function loadHistory() {
    const container = document.getElementById('history-list');
    container.innerHTML = '<div class="loading">Loading history...</div>';
    
    try {
        const data = await api.getHistory({ limit: 200 });
        
        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<p class="help-text">No audit history yet.</p>';
            historyState.allEvents = [];
            return;
        }
        
        // Store all events
        historyState.allEvents = data.history;
        
        // Setup filter event listeners (only once)
        setupHistoryFilters();
        
        // Render filtered events
        renderFilteredHistory();
        
    } catch (error) {
        container.innerHTML = `<p class="error-message">${error.message}</p>`;
    }
}

function setupHistoryFilters() {
    const searchInput = document.getElementById('history-search');
    const filterButtons = document.querySelectorAll('.history-filter-btn');
    const successCheckbox = document.getElementById('filter-success');
    const failedCheckbox = document.getElementById('filter-failed');
    const refreshBtn = document.getElementById('refresh-history-btn');
    
    // Search input
    if (!searchInput.hasAttribute('data-listener-attached')) {
        searchInput.addEventListener('input', (e) => {
            historyState.searchQuery = e.target.value.toLowerCase();
            renderFilteredHistory();
        });
        searchInput.setAttribute('data-listener-attached', 'true');
    }
    
    // Event type filter buttons
    filterButtons.forEach(btn => {
        if (!btn.hasAttribute('data-listener-attached')) {
            btn.addEventListener('click', () => {
                filterButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                historyState.eventTypeFilter = btn.dataset.filter;
                renderFilteredHistory();
            });
            btn.setAttribute('data-listener-attached', 'true');
        }
    });
    
    // Status checkboxes
    if (!successCheckbox.hasAttribute('data-listener-attached')) {
        successCheckbox.addEventListener('change', (e) => {
            historyState.showSuccess = e.target.checked;
            renderFilteredHistory();
        });
        successCheckbox.setAttribute('data-listener-attached', 'true');
    }
    
    if (!failedCheckbox.hasAttribute('data-listener-attached')) {
        failedCheckbox.addEventListener('change', (e) => {
            historyState.showFailed = e.target.checked;
            renderFilteredHistory();
        });
        failedCheckbox.setAttribute('data-listener-attached', 'true');
    }
    
    // Refresh button
    if (!refreshBtn.hasAttribute('data-listener-attached')) {
        refreshBtn.addEventListener('click', loadHistory);
        refreshBtn.setAttribute('data-listener-attached', 'true');
    }
}

function renderFilteredHistory() {
    const container = document.getElementById('history-list');
    
    // Apply filters
    let filtered = historyState.allEvents;
    
    // Filter by event type
    if (historyState.eventTypeFilter !== 'all') {
        filtered = filtered.filter(event => {
            const eventType = event.event_type || '';
            return eventType.startsWith(historyState.eventTypeFilter);
        });
    }
    
    // Filter by status
    filtered = filtered.filter(event => {
        const status = event.status || 'success';
        if (status === 'success' && !historyState.showSuccess) return false;
        if (status === 'failed' && !historyState.showFailed) return false;
        return true;
    });
    
    // Filter by search query
    if (historyState.searchQuery) {
        filtered = filtered.filter(event => {
            const searchableText = [
                event.event_type,
                event.resource_type,
                event.resource_id,
                event.action,
                JSON.stringify(event.details || {})
            ].join(' ').toLowerCase();
            
            return searchableText.includes(historyState.searchQuery);
        });
    }
    
    // Render results
    if (filtered.length === 0) {
        container.innerHTML = '<p class="help-text">No events match your filters.</p>';
        return;
    }
    
    container.innerHTML = filtered.map((event, index) => renderHistoryEvent(event, index)).join('');
}

function renderHistoryEvent(event, index) {
    const eventType = event.event_type || 'unknown';
    const status = event.status || 'success';
    const timestamp = formatTimestamp(event.timestamp);
    const icon = getEventIcon(eventType);
    const color = getEventColor(eventType);
    
    // Extract key info based on event type
    let primaryInfo = '';
    let secondaryInfo = '';
    
    if (eventType === 'job_execution') {
        primaryInfo = event.details?.command || 'Job executed';
        secondaryInfo = `${event.details?.items_returned || 0} items • ${event.details?.execution_ms || 0}ms`;
    } else if (eventType.startsWith('avatar_')) {
        primaryInfo = `${event.action} avatar`;
        secondaryInfo = event.details?.name || event.resource_id;
    } else if (eventType.startsWith('auth_')) {
        primaryInfo = `${event.action} authentication`;
        secondaryInfo = event.details?.method || '';
    } else if (eventType.startsWith('source_')) {
        primaryInfo = `${event.action} channel`;
        secondaryInfo = event.details?.name || event.resource_id;
    } else if (eventType.startsWith('config_')) {
        primaryInfo = `${event.action} configuration`;
        secondaryInfo = event.details?.updates?.join(', ') || '';
    } else {
        primaryInfo = event.event_type;
        secondaryInfo = event.resource_id;
    }
    
    return `
        <div class="history-event ${status}" data-index="${index}">
            <div class="history-event-header" onclick="toggleHistoryDetails(${index})">
                <div class="history-event-icon" style="background-color: ${color}20; color: ${color};">
                    ${icon}
                </div>
                <div class="history-event-info">
                    <div class="history-event-primary">${escapeHtml(primaryInfo)}</div>
                    <div class="history-event-secondary">${escapeHtml(secondaryInfo)}</div>
                </div>
                <div class="history-event-meta">
                    <span class="history-event-status status-${status}">${status}</span>
                    <span class="history-event-time">${timestamp}</span>
                    <span class="history-event-expand">▼</span>
                </div>
            </div>
            <div class="history-event-details" id="details-${index}" style="display: none;">
                ${renderEventDetails(event)}
            </div>
        </div>
    `;
}

function renderEventDetails(event) {
    let html = '<div class="event-details-content">';
    
    // Basic info
    html += '<div class="detail-row">';
    html += `<span class="detail-label">Event Type:</span>`;
    html += `<span class="detail-value">${escapeHtml(event.event_type || 'unknown')}</span>`;
    html += '</div>';
    
    html += '<div class="detail-row">';
    html += `<span class="detail-label">Resource:</span>`;
    html += `<span class="detail-value">${escapeHtml(event.resource_type || 'N/A')} / ${escapeHtml(event.resource_id || 'N/A')}</span>`;
    html += '</div>';
    
    html += '<div class="detail-row">';
    html += `<span class="detail-label">Action:</span>`;
    html += `<span class="detail-value">${escapeHtml(event.action || 'N/A')}</span>`;
    html += '</div>';
    
    html += '<div class="detail-row">';
    html += `<span class="detail-label">Actor:</span>`;
    html += `<span class="detail-value">${escapeHtml(event.actor || 'system')}</span>`;
    html += '</div>';
    
    // Error if present
    if (event.error) {
        html += '<div class="detail-row">';
        html += `<span class="detail-label">Error:</span>`;
        html += `<span class="detail-value error-text">${escapeHtml(event.error)}</span>`;
        html += '</div>';
    }
    
    // Details object
    if (event.details && Object.keys(event.details).length > 0) {
        html += '<div class="detail-row">';
        html += `<span class="detail-label">Details:</span>`;
        html += `<pre class="detail-json">${JSON.stringify(event.details, null, 2)}</pre>`;
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

function toggleHistoryDetails(index) {
    const detailsEl = document.getElementById(`details-${index}`);
    const eventEl = document.querySelector(`.history-event[data-index="${index}"]`);
    
    if (detailsEl.style.display === 'none') {
        detailsEl.style.display = 'block';
        eventEl.classList.add('expanded');
    } else {
        detailsEl.style.display = 'none';
        eventEl.classList.remove('expanded');
    }
}

function getEventIcon(eventType) {
    if (eventType === 'job_execution') return '⚙️';
    if (eventType.startsWith('avatar_created')) return '➕';
    if (eventType.startsWith('avatar_deleted')) return '🗑️';
    if (eventType.startsWith('avatar_')) return '👤';
    if (eventType.startsWith('auth_')) return '🔐';
    if (eventType.startsWith('source_added')) return '📥';
    if (eventType.startsWith('source_removed')) return '📤';
    if (eventType.startsWith('source_')) return '📡';
    if (eventType.startsWith('config_')) return '⚙️';
    return '📋';
}

function getEventColor(eventType) {
    if (eventType === 'job_execution') return '#3B82F6';    // blue-600
    if (eventType.startsWith('avatar_')) return '#9333EA';   // purple-600
    if (eventType.startsWith('auth_')) return '#EA580C';     // orange-600
    if (eventType.startsWith('source_')) return '#22C55E';   // green-500
    if (eventType.startsWith('config_')) return '#9333EA';   // purple-600
    return '#6B7280';                                        // gray-500
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000); // seconds
    
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    
    return date.toLocaleDateString();
}

// ====== Status ======
async function loadStatus() {
    const container = document.getElementById('status-display');
    container.innerHTML = '<div class="loading">Loading status...</div>';
    
    try {
        const data = await api.getStatus();
        
        const statusBadge = data.status === 'running' 
            ? '<span class="status-badge running">Running</span>'
            : '<span class="status-badge stopped">Stopped</span>';
        
        container.innerHTML = `
            <div class="status-item">
                <span class="status-label">Status</span>
                <span class="status-value">${statusBadge}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Version</span>
                <span class="status-value">${data.version || 'Unknown'}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Last Poll</span>
                <span class="status-value">${data.last_poll_at || 'Never'}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Jobs Executed</span>
                <span class="status-value">${data.jobs_executed || 0}</span>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<p class="error-message">${error.message}</p>`;
    }
}

// ====== Header Status Polling ======
let headerStatusInterval = null;

async function updateHeaderStatus() {
    const badge = document.getElementById('header-agent-status');
    const text = document.getElementById('header-status-text');
    if (!badge || !text) return;

    try {
        const data = await api.getStatus();
        const isRunning = data.status === 'running';
        badge.className = `header-status-badge ${isRunning ? 'running' : 'stopped'}`;
        text.textContent = isRunning ? 'Running' : 'Stopped';
    } catch {
        badge.className = 'header-status-badge unknown';
        text.textContent = 'Unknown';
    }
}

function startHeaderStatusPolling() {
    updateHeaderStatus();
    if (headerStatusInterval) clearInterval(headerStatusInterval);
    headerStatusInterval = setInterval(updateHeaderStatus, 10000);
}

function stopHeaderStatusPolling() {
    if (headerStatusInterval) {
        clearInterval(headerStatusInterval);
        headerStatusInterval = null;
    }
}

// ====== Avatar Source Management (New UX) ======

// State for source management
const sourceManagementState = {
    currentAvatarId: null,
    frequencyPresets: {},
    whitelistedSources: new Set(), // Track whitelisted source IDs
    allChannels: [], // Store all channels for filtering
    searchQuery: '',
    filterMode: 'all' // 'all', 'whitelisted', 'not-whitelisted'
};

async function openAvatarSettings(avatarId) {
    document.body.style.overflow = 'hidden';
    sourceManagementState.currentAvatarId = avatarId;
    
    // Find avatar name
    const avatars = await api.getAvatars();
    const avatar = avatars.avatars.find(a => a.id === avatarId);
    
    document.getElementById('settings-avatar-name').textContent = avatar ? avatar.name : avatarId;
    document.getElementById('avatar-settings-modal').classList.add('active');
    
    // Attach refresh button event listener (do once)
    const refreshBtn = document.getElementById('refresh-dialogs-btn');
    if (refreshBtn && !refreshBtn.hasAttribute('data-listener-attached')) {
        refreshBtn.addEventListener('click', refreshChannelsList);
        refreshBtn.setAttribute('data-listener-attached', 'true');
    }
    
    // Load channels (use cached data initially)
    await loadChannelsList(avatarId, false);
}

function closeAvatarSettingsModal() {
    document.body.style.overflow = '';
    document.getElementById('avatar-settings-modal').classList.remove('active');
    sourceManagementState.currentAvatarId = null;
}

async function loadChannelsList(avatarId, refresh = false) {
    const container = document.getElementById('channels-list');
    container.innerHTML = '<div class="loading">Loading channels...</div>';
    
    try {
        // Fetch dialogs (cached or fresh)
        const dialogsResponse = await api.request(`/avatars/${avatarId}/dialogs?limit=100&refresh=${refresh}`);
        const dialogs = dialogsResponse.dialogs || [];
        
        // Fetch current sources (whitelist)
        const sourcesResponse = await api.request(`/avatars/${avatarId}/sources`);
        sourceManagementState.frequencyPresets = sourcesResponse.frequency_presets;
        const sources = sourcesResponse.sources.items || [];
        
        // Build whitelist map
        const whitelistMap = {};
        sources.forEach(source => {
            whitelistMap[source.id] = source;
        });
        
        // Filter to only channels and groups
        const channelsAndGroups = dialogs.filter(d => d.type === 'channel' || d.type === 'group');
        
        if (channelsAndGroups.length === 0) {
            container.innerHTML = '<p class="help-text">No channels or groups found. Click "Refresh" to load from Telegram.</p>';
            sourceManagementState.allChannels = [];
            return;
        }
        
        // Store channels with whitelist status for filtering
        sourceManagementState.allChannels = channelsAndGroups.map(dialog => ({
            ...dialog,
            isWhitelisted: whitelistMap[dialog.id] !== undefined,
            frequency: whitelistMap[dialog.id]?.frequency_seconds || 300
        }));
        
        // Setup filter event listeners (only once)
        setupChannelFilters();
        
        // Render filtered channels
        renderFilteredChannels();
        
    } catch (error) {
        container.innerHTML = `<p class="error-message">${error.message}</p>`;
    }
}

function setupChannelFilters() {
    const searchInput = document.getElementById('channel-search');
    const filterButtons = document.querySelectorAll('.filter-btn');
    
    // Only setup if not already setup
    if (!searchInput.hasAttribute('data-listener-attached')) {
        searchInput.addEventListener('input', (e) => {
            sourceManagementState.searchQuery = e.target.value.toLowerCase();
            renderFilteredChannels();
        });
        searchInput.setAttribute('data-listener-attached', 'true');
    }
    
    filterButtons.forEach(btn => {
        if (!btn.hasAttribute('data-listener-attached')) {
            btn.addEventListener('click', () => {
                // Update active state
                filterButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Update filter mode
                sourceManagementState.filterMode = btn.dataset.filter;
                renderFilteredChannels();
            });
            btn.setAttribute('data-listener-attached', 'true');
        }
    });
}

function renderFilteredChannels() {
    const container = document.getElementById('channels-list');
    
    // Apply filters
    let filteredChannels = sourceManagementState.allChannels;
    
    // Apply search filter
    if (sourceManagementState.searchQuery) {
        filteredChannels = filteredChannels.filter(channel => 
            channel.name.toLowerCase().includes(sourceManagementState.searchQuery)
        );
    }
    
    // Apply whitelist filter
    if (sourceManagementState.filterMode === 'whitelisted') {
        filteredChannels = filteredChannels.filter(channel => channel.isWhitelisted);
    } else if (sourceManagementState.filterMode === 'not-whitelisted') {
        filteredChannels = filteredChannels.filter(channel => !channel.isWhitelisted);
    }
    
    // Render results
    if (filteredChannels.length === 0) {
        container.innerHTML = '<p class="help-text">No channels match your filters.</p>';
        return;
    }
    
    container.innerHTML = filteredChannels.map(dialog => {
        return `
            <div class="channel-item">
                <img src="${dialog.avatar_url || '/api/cache/avatars/placeholder.png'}" 
                     alt="${escapeHtml(dialog.name)}" 
                     class="channel-avatar"
                     onerror="this.src='/api/cache/avatars/placeholder.png'">
                
                <div class="channel-info">
                    <h4>${escapeHtml(dialog.name)}</h4>
                    <span class="channel-meta">
                        ${dialog.type} ${dialog.members_count ? `• ${dialog.members_count} members` : ''}
                    </span>
                </div>
                
                <div class="channel-controls">
                    <label class="toggle-switch">
                        <input type="checkbox" 
                               ${dialog.isWhitelisted ? 'checked' : ''}
                               onchange="toggleChannelWhitelist('${dialog.id}', '${escapeHtml(dialog.name)}', '${dialog.type}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                    
                    <select class="frequency-select" 
                            ${!dialog.isWhitelisted ? 'style="display:none;"' : ''}
                            id="freq-${dialog.id}"
                            onchange="updateChannelFrequency('${dialog.id}', this.value)">
                        ${Object.entries(sourceManagementState.frequencyPresets).map(([label, seconds]) => 
                            `<option value="${seconds}" ${dialog.frequency === seconds ? 'selected' : ''}>${label}</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
        `;
    }).join('');
}

async function refreshChannelsList() {
    if (!sourceManagementState.currentAvatarId) return;
    
    const btn = document.getElementById('refresh-dialogs-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Refreshing...';
    btn.disabled = true;
    
    try {
        await loadChannelsList(sourceManagementState.currentAvatarId, true);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function toggleChannelWhitelist(channelId, channelName, channelType, isWhitelisted) {
    if (!sourceManagementState.currentAvatarId) return;
    
    try {
        if (isWhitelisted) {
            // Add to whitelist
            await api.request(`/avatars/${sourceManagementState.currentAvatarId}/sources`, {
                method: 'POST',
                body: JSON.stringify({
                    id: channelId,
                    name: channelName,
                    type: channelType,
                    frequency_seconds: 300 // Default: 5 minutes
                })
            });
            
            // Show frequency selector
            const freqSelect = document.getElementById(`freq-${channelId}`);
            if (freqSelect) freqSelect.style.display = 'block';
            
        } else {
            // Remove from whitelist
            await api.request(`/avatars/${sourceManagementState.currentAvatarId}/sources/${channelId}`, {
                method: 'DELETE'
            });
            
            // Hide frequency selector
            const freqSelect = document.getElementById(`freq-${channelId}`);
            if (freqSelect) freqSelect.style.display = 'none';
        }
        
    } catch (error) {
        alert('Failed to update whitelist: ' + error.message);
        // Reload to revert UI state
        await loadChannelsList(sourceManagementState.currentAvatarId, false);
    }
}

async function updateChannelFrequency(channelId, frequencySeconds) {
    if (!sourceManagementState.currentAvatarId) return;
    
    try {
        await api.request(`/avatars/${sourceManagementState.currentAvatarId}/sources/${channelId}`, {
            method: 'PUT',
            body: JSON.stringify({
                frequency_seconds: parseInt(frequencySeconds)
            })
        });
        
    } catch (error) {
        alert('Failed to update frequency: ' + error.message);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ====== Event Listeners ======
document.addEventListener('DOMContentLoaded', () => {
    // Check if already logged in
    if (state.token) {
        showPage('dashboard-page');
        document.getElementById('username-display').textContent = state.username;
        startHeaderStatusPolling();
        loadConfig();
    } else {
        showPage('login-page');
    }
    
    // Login
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('logout-btn').addEventListener('click', logout);
    
    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => showTab(tab.dataset.tab));
    });
    
    // Config
    document.getElementById('config-form').addEventListener('submit', handleConfigSubmit);
    document.getElementById('start-agent-btn').addEventListener('click', handleStartAgent);
    document.getElementById('stop-agent-btn').addEventListener('click', handleStopAgent);
    
    // Avatars
    document.getElementById('add-avatar-btn').addEventListener('click', openAddAvatarModal);
    document.querySelector('.modal-close').addEventListener('click', closeAddAvatarModal);
    
    document.querySelectorAll('.auth-method-btn').forEach(btn => {
        btn.addEventListener('click', () => switchAuthMethod(btn.dataset.method));
    });
    
    document.getElementById('start-qr-auth-btn').addEventListener('click', handleStartQRAuth);
    document.getElementById('cancel-qr-auth-btn').addEventListener('click', handleCancelQRAuth);
    document.getElementById('start-phone-auth-btn').addEventListener('click', handleStartPhoneAuth);
    document.getElementById('complete-phone-auth-btn').addEventListener('click', handleCompletePhoneAuth);
    
    // Blacklist
    document.getElementById('save-blacklist-btn').addEventListener('click', handleSaveBlacklist);
    
    // Source management - refresh button (will be available after modal opens)
    // Event listener added dynamically when modal is shown
    
    // Close modals on background click
    document.getElementById('add-avatar-modal').addEventListener('click', (e) => {
        if (e.target.id === 'add-avatar-modal') {
            closeAddAvatarModal();
        }
    });
    
    document.getElementById('avatar-settings-modal').addEventListener('click', (e) => {
        if (e.target.id === 'avatar-settings-modal') {
            closeAvatarSettingsModal();
        }
    });
});
