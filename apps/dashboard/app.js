/**
 * Vindex - SentinelShield AI Dashboard
 * JavaScript for API calls, interactivity, and theme toggle
 */

const API_BASE = '/api/v1';

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

    stats.by_status.forEach(s => {
        if (s.status && s.status.toUpperCase().includes('AUTO_SUBMIT')) {
            autoCount = s.count;
        }
        if (s.status && s.status.toUpperCase().includes('ESCALAT')) {
            escalateCount = s.count;
        }
    });

    const autoRate = total > 0 ? Math.round((autoCount / total) * 100) : 0;
    const escalateRate = total > 0 ? Math.round((escalateCount / total) * 100) : 0;

    document.getElementById('metric-auto').textContent = autoRate + '%';
    document.getElementById('metric-escalate').textContent = escalateRate + '%';
    document.getElementById('metric-recovery').textContent = 'Rs. 0';
}

async function updateDisputeStream() {
    const data = await fetchDisputes();
    const list = document.getElementById('dispute-list');

    if (!data.disputes || data.disputes.length === 0) {
        list.innerHTML = '<div class="empty-state">No disputes found. Send a webhook to create one.</div>';
        return;
    }

    list.innerHTML = data.disputes.map(d => `
        <div class="dispute-item" data-id="${d.id}" onclick="selectDispute('${d.id}')">
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

    document.getElementById('inspector-content').innerHTML = `
        <div class="inspector-grid">
            <div class="inspector-panel">
                <h3>Order Details</h3>
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
                <h3>Evaluation Results</h3>
                <div class="win-gauge">
                    <div class="gauge-bar">
                        <div class="gauge-fill" style="width: ${winProb}%"></div>
                    </div>
                    <div class="gauge-label">
                        <span>P(win)</span>
                        <span>${winProb}%</span>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 0.75rem;">
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
                    <button class="btn-approve" onclick="reviewDispute('${detail.id}', 'approve')">Approve Contest</button>
                    <button class="btn-dismiss" onclick="reviewDispute('${detail.id}', 'dismiss')">Dismiss</button>
                </div>
            </div>
        </div>
    `;
}

async function reviewDispute(disputeId, action) {
    try {
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
        }
    } catch (err) {
        console.error('Review error:', err);
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

    let progressVal = 0;
    const progressInterval = setInterval(() => {
        if (progressVal < 90) {
            progressVal += 5;
            progressFill.style.width = progressVal + '%';
            progressText.textContent = Math.round(progressVal * 2) + '/200';
        }
    }, 200);

    const data = await triggerBenchmark();

    clearInterval(progressInterval);

    if (data && data.metrics) {
        const m = data.metrics;
        progressFill.style.width = '100%';
        progressText.textContent = '200/200';
        status.textContent = 'Completed';

        document.getElementById('result-accuracy').textContent =
            (m.accuracy * 100).toFixed(1) + '%';
        document.getElementById('result-awb').textContent =
            (m.extraction.awb_precision * 100).toFixed(1) + '%';
        document.getElementById('result-latency').textContent =
            m.latency.mean_seconds.toFixed(3) + 's';
        document.getElementById('result-yield').textContent =
            'Rs. ' + m.financial.net_yield_inr.toLocaleString('en-IN');

        results.style.display = 'grid';
    } else {
        status.textContent = 'Failed';
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
    });
    document.getElementById('benchmark-btn').addEventListener('click', runBenchmark);

    updateMetricCards();
    updateDisputeStream();

    setInterval(() => {
        updateDisputeStream();
        updateMetricCards();
    }, 10000);
});
