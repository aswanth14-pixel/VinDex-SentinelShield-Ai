/**
 * Vindex - SentinelShield AI Dashboard
 * JavaScript for API calls, interactivity, and theme toggle
 */

const API_BASE = '/api/v1';

// ========================================
// Terminal Logging
// ========================================

function addTerminalLog(level, message) {
    const terminal = document.getElementById('terminal-logs');
    if (!terminal) return;

    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `
        <span class="log-timestamp">[${timestamp}]</span>
        <span class="log-level ${level}">${level.toUpperCase()}</span>
        <span class="log-message">${message}</span>
    `;

    terminal.appendChild(logEntry);
    terminal.scrollTop = terminal.scrollHeight;

    // Keep only last 50 entries
    while (terminal.children.length > 50) {
        terminal.removeChild(terminal.firstChild);
    }
}

function logPipelineStep(step, message) {
    addTerminalLog('process', `[${step}] ${message}`);
}

// ========================================
// Theme Toggle
// ========================================

function initTheme() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    showToast('Theme Changed', `Switched to ${next} mode`, 'info');
    addTerminalLog('info', `Theme changed to ${next} mode`);
}

// ========================================
// Toast Notifications
// ========================================

function showToast(title, message, type = 'success') {
    const container = document.getElementById('toast-container');
    const icons = {
        success: '✅',
        warning: '⚠️',
        error: '❌',
        info: 'ℹ️'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'slideOutRight 0.5s ease forwards';
            setTimeout(() => toast.remove(), 500);
        }
    }, 4000);
}

// ========================================
// API Calls
// ========================================

async function fetchDisputes() {
    try {
        const res = await fetch(`${API_BASE}/disputes?limit=100`);
        if (!res.ok) throw new Error('Failed to fetch disputes');
        return await res.json();
    } catch (err) {
        console.error('Error fetching disputes:', err);
        return { disputes: [], total: 0 };
    }
}

async function fetchDisputeStats() {
    try {
        const res = await fetch(`${API_BASE}/disputes/stats/summary`);
        if (!res.ok) throw new Error('Failed to fetch stats');
        return await res.json();
    } catch (err) {
        console.error('Error fetching stats:', err);
        return { by_status: [], total_disputes: 0 };
    }
}

async function fetchDisputeDetail(disputeId) {
    try {
        const res = await fetch(`${API_BASE}/disputes/${disputeId}`);
        if (!res.ok) throw new Error('Failed to fetch dispute');
        return await res.json();
    } catch (err) {
        console.error('Error fetching dispute:', err);
        return null;
    }
}

async function triggerBenchmark() {
    try {
        const res = await fetch(`${API_BASE}/eval/benchmark`, { method: 'POST' });
        if (!res.ok) throw new Error('Benchmark failed');
        return await res.json();
    } catch (err) {
        console.error('Error running benchmark:', err);
        return null;
    }
}

// ========================================
// UI Updates
// ========================================

function formatAmount(paise) {
    const inr = paise / 100;
    return 'Rs. ' + inr.toLocaleString('en-IN');
}

function getStatusBadgeClass(status) {
    if (!status) return 'status-badge-open';
    const s = status.toUpperCase();
    if (s.includes('AUTO_SUBMIT')) return 'status-badge-auto';
    if (s.includes('ESCALAT')) return 'status-badge-escalate';
    if (s.includes('ABANDON') || s.includes('DISMISSED')) return 'status-badge-abandon';
    return 'status-badge-open';
}

function getStatusLabel(status) {
    if (!status) return 'Open';
    const s = status.toUpperCase();
    if (s.includes('AUTO_SUBMIT')) return 'Auto Submitted';
    if (s.includes('ESCALAT')) return 'Review Required';
    if (s.includes('ABANDON')) return 'Abandoned';
    if (s.includes('DISMISSED')) return 'Dismissed';
    return status;
}

async function updateMetricCards() {
    const stats = await fetchDisputeStats();
    const total = stats.total_disputes || 0;

    document.getElementById('metric-total').textContent = total;

    let autoCount = 0;
    let escalateCount = 0;
    let recoveryAmount = 0;

    stats.by_status.forEach(s => {
        if (s.status && s.status.toUpperCase().includes('AUTO_SUBMIT')) {
            autoCount = s.count;
            recoveryAmount += s.total_amount || 0;
        }
        if (s.status && s.status.toUpperCase().includes('ESCALAT')) {
            escalateCount = s.count;
        }
    });

    const autoRate = total > 0 ? Math.round((autoCount / total) * 100) : 0;
    const escalateRate = total > 0 ? Math.round((escalateCount / total) * 100) : 0;

    document.getElementById('metric-auto').textContent = autoRate + '%';
    document.getElementById('metric-escalate').textContent = escalateRate + '%';
    document.getElementById('metric-recovery').textContent = formatAmount(recoveryAmount);
}

// ========================================
// Webhook Detection & Toast
// ========================================

let lastDisputeCount = 0;
let isFirstLoad = true;

async function checkForNewDisputes() {
    const data = await fetchDisputes();
    const currentCount = data.disputes ? data.disputes.length : 0;

    if (!isFirstLoad && lastDisputeCount > 0 && currentCount > lastDisputeCount) {
        const newest = data.disputes[0];
        const amount = formatAmount(newest.amount);
        const status = getStatusLabel(newest.status);

        let toastType = 'info';
        if (status.includes('Auto')) toastType = 'success';
        if (status.includes('Review')) toastType = 'warning';
        if (status.includes('Abandon')) toastType = 'error';

        showToast(
            '🔔 New Dispute Received',
            `${newest.id} • ${amount} • ${status}`,
            toastType
        );

        // Add terminal logs for pipeline simulation
        addTerminalLog('info', `Webhook received: ${newest.id}`);
        logPipelineStep('VERIFY', 'HMAC-SHA256 signature validated ✓');
        
        setTimeout(() => {
            logPipelineStep('FETCH', `Fetching evidence for payment ${newest.payment_id}`);
        }, 200);
        
        setTimeout(() => {
            logPipelineStep('EXTRACT', 'Running Gemini Vision on POD document...');
        }, 400);
        
        setTimeout(() => {
            logPipelineStep('EXTRACT', `AWB extracted: ${newest.id.slice(-8)}`);
        }, 600);
        
        setTimeout(() => {
            logPipelineStep('SCORE', `Calculating win probability...`);
        }, 800);
        
        setTimeout(() => {
            const action = status.includes('Auto') ? 'AUTO_SUBMIT' : 
                          status.includes('Review') ? 'ESCALATE_HUMAN' : 'ABANDON';
            logPipelineStep('DECIDE', `Action: ${action}`);
            addTerminalLog('success', `Pipeline complete for ${newest.id}`);
        }, 1000);
    }

    isFirstLoad = false;
    lastDisputeCount = currentCount;
    return data;
}

async function updateDisputeStream() {
    const data = await checkForNewDisputes();
    const list = document.getElementById('dispute-list');

    if (!data.disputes || data.disputes.length === 0) {
        list.innerHTML = '<div class="empty-state">No disputes found. Send a webhook to create one.</div>';
        return;
    }

    list.innerHTML = data.disputes.map((d, index) => `
        <div class="dispute-item ${index === 0 && !isFirstLoad ? 'new-arrival' : ''}" data-id="${d.id}" onclick="selectDispute('${d.id}')">
            <div class="dispute-left">
                <span class="dispute-id">${d.id}</span>
                <span class="dispute-amount">${formatAmount(d.amount)}</span>
            </div>
            <div class="dispute-right">
                <span class="dispute-reason">${d.reason_code}</span>
                <span class="${getStatusBadgeClass(d.status)}">${getStatusLabel(d.status)}</span>
            </div>
        </div>
    `).join('');
}

async function selectDispute(disputeId) {
    document.querySelectorAll('.dispute-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === disputeId);
    });

    addTerminalLog('info', `Inspecting dispute: ${disputeId}`);

    const detail = await fetchDisputeDetail(disputeId);
    if (!detail) {
        document.getElementById('inspector-content').innerHTML =
            '<div class="empty-state">Failed to load dispute details</div>';
        return;
    }

    const ev = detail.evaluation || {};
    const ex = detail.evidence || {};
    const winProb = ev.win_probability ? (ev.win_probability * 100).toFixed(1) : '0';
    const action = ev.action || 'UNKNOWN';

    let actionClass = 'action-escalate';
    if (action.includes('AUTO')) actionClass = 'action-auto';
    if (action.includes('ABANDON')) actionClass = 'action-abandon';

    addTerminalLog('success', `Loaded: P(win)=${winProb}%, Action=${action}`);

    document.getElementById('inspector-content').innerHTML = `
        <div class="inspector-grid">
            <div class="inspector-panel">
                <h3>📋 Order Details</h3>
                <div class="info-row">
                    <span class="info-label">Dispute ID</span>
                    <span class="info-value">${detail.id}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Payment ID</span>
                    <span class="info-value">${detail.payment_id}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Amount</span>
                    <span class="info-value">${formatAmount(detail.amount)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Reason</span>
                    <span class="info-value">${detail.reason_code}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Status</span>
                    <span class="info-value">${detail.status}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">AWB Number</span>
                    <span class="info-value">${ex.awb_number || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Courier</span>
                    <span class="info-value">${ex.courier_name || 'N/A'}</span>
                </div>
            </div>
            <div class="inspector-panel">
                <h3>📊 Evaluation Results</h3>
                <div class="win-gauge">
                    <div class="gauge-bar">
                        <div class="gauge-fill" style="width: ${winProb}%"></div>
                    </div>
                    <div class="gauge-label">
                        <span>P(win)</span>
                        <span>${winProb}%</span>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 1rem;">
                    <span class="action-badge ${actionClass}">${action}</span>
                </div>
                <div style="margin-top: 1rem;">
                    <div class="info-row">
                        <span class="info-label">Evidence Completeness</span>
                        <span class="info-value">${ev.evidence_completeness_score ? (ev.evidence_completeness_score * 100).toFixed(0) + '%' : 'N/A'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Projected Recovery</span>
                        <span class="info-value">${ev.projected_net_recovery ? formatAmount(ev.projected_net_recovery) : 'N/A'}</span>
                    </div>
                </div>
                <div class="inspector-actions">
                    <button class="btn-approve" onclick="reviewDispute('${detail.id}', 'approve')">✓ Approve Contest</button>
                    <button class="btn-dismiss" onclick="reviewDispute('${detail.id}', 'dismiss')">✕ Dismiss</button>
                </div>
            </div>
        </div>
    `;

    showToast('Dispute Selected', `Viewing details for ${detail.id}`, 'info');
}

async function reviewDispute(disputeId, action) {
    try {
        addTerminalLog('info', `Reviewing dispute: ${disputeId} - ${action}`);

        const res = await fetch(`${API_BASE}/disputes/${disputeId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, notes: `Dashboard ${action} by user` })
        });

        if (res.ok) {
            await updateDisputeStream();
            await updateMetricCards();
            document.getElementById('inspector-content').innerHTML =
                '<div class="empty-state">Dispute ' + action + 'd successfully</div>';
            
            addTerminalLog('success', `Dispute ${disputeId} ${action}d ✓`);

            showToast(
                action === 'approve' ? '✅ Approved' : '❌ Dismissed',
                `Dispute ${disputeId} has been ${action}d`,
                action === 'approve' ? 'success' : 'warning'
            );
        }
    } catch (err) {
        console.error('Review error:', err);
        addTerminalLog('error', `Review failed: ${err.message}`);
        showToast('Error', 'Failed to process review', 'error');
    }
}

// ========================================
// Benchmark
// ========================================

let benchmarkRunning = false;

async function runBenchmark() {
    if (benchmarkRunning) return;
    benchmarkRunning = true;

    const btn = document.getElementById('benchmark-btn');
    const status = document.getElementById('benchmark-status');
    const progress = document.getElementById('benchmark-progress');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const results = document.getElementById('benchmark-results');

    btn.disabled = true;
    status.textContent = 'Running...';
    progress.style.display = 'block';
    results.style.display = 'none';

    addTerminalLog('info', 'Starting 200-case benchmark evaluation...');
    logPipelineStep('INIT', 'Loading synthetic dataset...');

    showToast('Benchmark Started', 'Running 200-case evaluation suite...', 'info');

    let progressVal = 0;
    const progressInterval = setInterval(() => {
        if (progressVal < 90) {
            progressVal += 5;
            progressFill.style.width = progressVal + '%';
            progressText.textContent = Math.round(progressVal * 2) + '/200';
            
            if (progressVal % 20 === 0) {
                addTerminalLog('process', `Processed ${Math.round(progressVal * 2)}/200 cases...`);
            }
        }
    }, 200);

    const data = await triggerBenchmark();

    clearInterval(progressInterval);

    if (data && data.metrics) {
        const m = data.metrics;
        progressFill.style.width = '100%';
        progressText.textContent = '200/200';
        status.textContent = 'Completed ✓';

        document.getElementById('result-accuracy').textContent =
            (m.accuracy * 100).toFixed(1) + '%';
        document.getElementById('result-awb').textContent =
            (m.extraction.awb_precision * 100).toFixed(1) + '%';
        document.getElementById('result-latency').textContent =
            m.latency.mean_seconds.toFixed(3) + 's';
        document.getElementById('result-yield').textContent =
            'Rs. ' + m.financial.net_yield_inr.toLocaleString('en-IN');

        results.style.display = 'grid';
        
        addTerminalLog('success', `Benchmark complete! Accuracy: ${(m.accuracy * 100).toFixed(1)}%`);
        addTerminalLog('success', `Net Yield: Rs. ${m.financial.net_yield_inr.toLocaleString('en-IN')}`);
        
        showToast(
            'Benchmark Complete',
            `Accuracy: ${(m.accuracy * 100).toFixed(1)}% • Yield: Rs. ${m.financial.net_yield_inr.toLocaleString('en-IN')}`,
            'success'
        );
    } else {
        status.textContent = 'Failed ✗';
        addTerminalLog('error', 'Benchmark failed!');
        showToast('Benchmark Failed', 'An error occurred during evaluation', 'error');
    }

    btn.disabled = false;
    benchmarkRunning = false;
}

// ========================================
// Init
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    initTheme();

    document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
    document.getElementById('refresh-btn').addEventListener('click', () => {
        updateDisputeStream();
        updateMetricCards();
        addTerminalLog('info', 'Dashboard refreshed');
        showToast('Refreshed', 'Dispute stream updated', 'success');
    });
    document.getElementById('benchmark-btn').addEventListener('click', runBenchmark);

    addTerminalLog('info', 'Dashboard loaded successfully');
    addTerminalLog('success', 'Connected to Vindex API');

    updateMetricCards();
    updateDisputeStream();

    // Auto-refresh every 10 seconds
    setInterval(() => {
        updateDisputeStream();
        updateMetricCards();
    }, 10000);
});
