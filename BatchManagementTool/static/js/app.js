/**
 * HP Batch Management Dashboard — Main JavaScript
 * Premium Edition: Charts, Tables, Search, Filtering, Detail Panel
 */

// ============================================================
// Utility helpers
// ============================================================

function debounce(fn, ms = 200) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function highlightText(text, query) {
    if (!query) return escapeHtml(text);
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(${escaped})`, 'gi');
    return escapeHtml(text).replace(re, '<mark>$1</mark>');
}

function formatDateLabel(isoDate) {
    if (!isoDate) return '';
    const parts = isoDate.split('-');
    if (parts.length === 3) return `${parseInt(parts[1])}/${parseInt(parts[2])}`;
    return isoDate;
}

// ============================================================
// Count-up animation for KPI numbers
// ============================================================

function animateCountUp(el) {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || '';
    const decimals = el.dataset.decimals ? parseInt(el.dataset.decimals) : 0;
    const duration = 800;
    const start = performance.now();

    function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = target * eased;
        el.textContent = current.toFixed(decimals) + suffix;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-count-up]').forEach(animateCountUp);
});

// ============================================================
// ECharts Theme Setup
// ============================================================

const CHART_THEME_DARK = {
    bg: 'transparent',
    textColor: '#a1a1aa',
    textColorDim: '#71717a',
    borderColor: 'rgba(255,255,255,0.06)',
    axisLineColor: 'rgba(255,255,255,0.06)',
    splitLineColor: 'rgba(255,255,255,0.04)',
    accent: '#6366f1',
    accentLight: '#818cf8',
    success: '#10b981',
    warning: '#f59e0b',
    destructive: '#ef4444',
    colors: ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6'],
    fontMono: 'JetBrains Mono, monospace',
    fontBody: 'Inter, system-ui, sans-serif',
    tooltipBg: '#18181b',
    tooltipBorder: 'rgba(255,255,255,0.08)',
    tooltipText: '#fafafa',
    labelColor: '#fafafa',
    cardBg: '#09090b',
};

const CHART_THEME_LIGHT = {
    bg: 'transparent',
    textColor: '#4a4a68',
    textColorDim: '#6b7280',
    borderColor: 'rgba(0,0,0,0.08)',
    axisLineColor: 'rgba(0,0,0,0.1)',
    splitLineColor: 'rgba(0,0,0,0.05)',
    accent: '#4f46e5',
    accentLight: '#6366f1',
    success: '#059669',
    warning: '#d97706',
    destructive: '#dc2626',
    colors: ['#4f46e5', '#059669', '#d97706', '#db2777', '#0891b2', '#7c3aed'],
    fontMono: 'JetBrains Mono, monospace',
    fontBody: 'Inter, system-ui, sans-serif',
    tooltipBg: '#ffffff',
    tooltipBorder: 'rgba(0,0,0,0.1)',
    tooltipText: '#1a1a2e',
    labelColor: '#1a1a2e',
    cardBg: '#f8f9fa',
};

function getChartTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? CHART_THEME_LIGHT : CHART_THEME_DARK;
}

// Keep CHART_THEME as a reference (backward compat) — will be refreshed dynamically
let CHART_THEME = getChartTheme();

function chartBaseGrid(opts = {}) {
    return {
        left: opts.left || 50,
        right: opts.right || 20,
        top: opts.top || 30,
        bottom: opts.bottom || 40,
        containLabel: false,
    };
}

function chartAxisStyle() {
    const t = getChartTheme();
    return {
        axisLine: { lineStyle: { color: t.axisLineColor } },
        axisLabel: { color: t.textColor, fontSize: 11, fontFamily: t.fontBody },
        splitLine: { lineStyle: { color: t.splitLineColor } },
        axisTick: { show: false },
    };
}

// ============================================================
// Detail Panel
// ============================================================

const DetailPanel = {
    overlay: null,
    panel: null,

    init() {
        this.overlay = document.getElementById('detail-overlay');
        this.panel = document.getElementById('detail-panel');
        if (!this.overlay || !this.panel) return;

        this.overlay.addEventListener('click', () => this.close());
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.close();
        });

        const closeBtn = this.panel.querySelector('.detail-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.close());
    },

    open(contentHtml) {
        if (!this.panel) return;
        const body = this.panel.querySelector('.detail-body');
        if (body) body.innerHTML = contentHtml;
        this.overlay.classList.add('open');
        this.panel.classList.add('open');
    },

    close() {
        if (!this.overlay) return;
        this.overlay.classList.remove('open');
        this.panel.classList.remove('open');
    }
};

// ============================================================
// Orders Table
// ============================================================

const OrdersTable = {
    allOrders: [],
    filtered: [],
    sortCol: '',
    sortAsc: true,
    page: 1,
    pageSize: 50,
    searchQuery: '',
    activeFilters: { system: [], shift: [], type: [], status: [], wc: [], date: [] },

    async init() {
        try {
            const resp = await fetch('/api/orders');
            this.allOrders = await resp.json();
        } catch { this.allOrders = []; }
        this.filtered = [...this.allOrders];
        this.populateDateFilter();
        this.bindEvents();
        this.render();
    },

    populateDateFilter() {
        const container = document.getElementById('date-filter-group');
        if (!container) return;
        const dates = [...new Set(this.allOrders.map(o => o.production_date).filter(Boolean))].sort();
        container.innerHTML = '';
        dates.forEach(d => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn';
            btn.dataset.filter = d;
            btn.dataset.filterGroup = 'date';
            btn.dataset.isDynamic = 'true';
            const parts = d.split('-');
            btn.textContent = `${parseInt(parts[1])}/${parseInt(parts[2])}`;
            container.appendChild(btn);
        });
    },

    bindEvents() {
        const searchInput = document.getElementById('orders-search');
        if (searchInput) {
            searchInput.addEventListener('input', debounce((e) => {
                this.searchQuery = e.target.value.trim();
                this.page = 1;
                this.applyFilters();
            }));
            document.addEventListener('keydown', (e) => {
                if (e.key === '/' && document.activeElement !== searchInput) {
                    e.preventDefault();
                    searchInput.focus();
                }
            });
        }

        const clearBtn = document.getElementById('orders-search-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const input = document.getElementById('orders-search');
                if (input) { input.value = ''; this.searchQuery = ''; this.page = 1; this.applyFilters(); }
            });
        }

        document.querySelectorAll('.filter-btn[data-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                const group = btn.dataset.filterGroup;
                const value = btn.dataset.filter;
                btn.classList.toggle('active');
                if (btn.classList.contains('active')) {
                    if (!this.activeFilters[group]) this.activeFilters[group] = [];
                    this.activeFilters[group].push(value);
                } else {
                    this.activeFilters[group] = this.activeFilters[group].filter(v => v !== value);
                }
                this.page = 1;
                this.applyFilters();
            });
        });

        const clearFilters = document.getElementById('clear-filters');
        if (clearFilters) {
            clearFilters.addEventListener('click', () => {
                this.activeFilters = { system: [], shift: [], type: [], status: [], wc: [], date: [] };
                document.querySelectorAll('.filter-btn.active').forEach(b => b.classList.remove('active'));
                this.page = 1;
                this.applyFilters();
            });
        }

        const exportBtn = document.getElementById('export-excel');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportToExcel());
        }
    },

    applyFilters() {
        let data = [...this.allOrders];
        const q = this.searchQuery.toLowerCase();

        if (q) {
            data = data.filter(o =>
                (o.order_number || '').toLowerCase().includes(q) ||
                (o.material || '').toLowerCase().includes(q) ||
                (o.material_description || '').toLowerCase().includes(q) ||
                (o.wip_code || '').toLowerCase().includes(q) ||
                (o.batch_id || '').toLowerCase().includes(q)
            );
        }

        const f = this.activeFilters;
        if (f.system && f.system.length) {
            data = data.filter(o => f.system.includes(o.assigned_system));
        }
        if (f.shift && f.shift.length) {
            data = data.filter(o => f.shift.includes(o.shift));
        }
        if (f.type && f.type.length) {
            data = data.filter(o => {
                const t = (o.product_type || '').toLowerCase();
                return f.type.some(fv => t.includes(fv.toLowerCase()));
            });
        }
        if (f.wc && f.wc.length) {
            data = data.filter(o => f.wc.includes(o.work_center));
        }
        if (f.date && f.date.length) {
            data = data.filter(o => f.date.includes(o.production_date));
        }

        this.filtered = data;
        this.applySorting();
        this.render();
    },

    applySorting() {
        if (!this.sortCol) return;
        const col = this.sortCol;
        const asc = this.sortAsc;
        this.filtered.sort((a, b) => {
            let va = a[col], vb = b[col];
            if (typeof va === 'number' && typeof vb === 'number') return asc ? va - vb : vb - va;
            va = String(va || ''); vb = String(vb || '');
            return asc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
    },

    sort(col) {
        if (this.sortCol === col) { this.sortAsc = !this.sortAsc; }
        else { this.sortCol = col; this.sortAsc = true; }
        this.applyFilters();
    },

    render() {
        const tbody = document.getElementById('orders-tbody');
        const countEl = document.getElementById('orders-count');
        if (!tbody) return;

        const total = this.filtered.length;
        const start = (this.page - 1) * this.pageSize;
        const end = Math.min(start + this.pageSize, total);
        const slice = this.filtered.slice(start, end);
        const q = this.searchQuery;

        if (countEl) {
            countEl.textContent = `${total ? start + 1 : 0}-${end} / ${total} (${this.allOrders.length} total)`;
        }

        tbody.innerHTML = slice.map((o, idx) => {
            const alertClass = o.alerts && o.alerts.length ? (
                o.alerts.some(a => a.includes('超出') || a.includes('超限')) ? 'has-critical-alert' : 'has-alert'
            ) : '';

            const statusInfo = this._parseStatus(o.decision_explain);
            const dotClass = statusInfo.dotClass;

            return `<tr class="${alertClass} animate-in" style="animation-delay:${idx * 15}ms" data-order-idx="${start + idx}">
                <td class="col-mono">${highlightText(o.order_number, q)}</td>
                <td>${highlightText(o.material, q)}</td>
                <td title="${escapeHtml(o.material_description)}">${highlightText((o.material_description || '').substring(0, 20), q)}</td>
                <td>${o.work_center}</td>
                <td>${o.shift}</td>
                <td class="col-mono">${o.start || ''}</td>
                <td class="col-mono">${o.end || ''}</td>
                <td class="col-mono">${o.msu_demand}</td>
                <td>${o.assigned_system}</td>
                <td class="col-mono">${highlightText(o.batch_id, q)}</td>
                <td><span class="status-dot ${dotClass}"></span>${statusInfo.label}</td>
                <td>${o.alerts && o.alerts.length ? '⚠' : ''}</td>
            </tr>`;
        }).join('');

        tbody.querySelectorAll('tr').forEach(tr => {
            tr.addEventListener('click', () => {
                const idx = parseInt(tr.dataset.orderIdx);
                this.showDetail(this.filtered[idx]);
            });
        });

        this.renderPagination(total);
    },

    _parseStatus(explain) {
        if (!explain) return { dotClass: '', label: '' };
        if (explain.includes('IN_PREFERRED')) return { dotClass: 'preferred', label: 'PREFERRED' };
        if (explain.includes('IN_HARD_ONLY')) return { dotClass: 'hard-only', label: 'HARD' };
        if (explain.includes('OUTSIDE_HARD')) return { dotClass: 'outside', label: 'OUTSIDE' };
        if (explain.includes('ABOVE_PREFERRED')) return { dotClass: 'hard-only', label: 'ABOVE_PREF' };
        return { dotClass: '', label: '' };
    },

    showDetail(order) {
        if (!order) return;

        let target = '';
        let load = order.msu_demand || 0;
        const targetMatch = (order.decision_explain || '').match(/Target[=:]?\s*([\d.]+)/i);
        if (targetMatch) target = targetMatch[1];
        const tVal = parseFloat(target) || 0;
        const ratio = tVal > 0 ? (load / tVal * 100) : 0;
        const barColor = ratio >= 90 ? 'green' : ratio >= 70 ? 'yellow' : 'red';

        const html = `
            <div class="detail-title">\u{1F4C4} Order ${escapeHtml(order.order_number)}</div>
            <div class="detail-section">
                <div class="detail-section-title">Basic Info</div>
                <div class="detail-row"><span class="detail-label">Material</span><span class="detail-value">${escapeHtml(order.material)}</span></div>
                <div class="detail-row"><span class="detail-label">Description</span><span class="detail-value">${escapeHtml(order.material_description || '-')}</span></div>
                <div class="detail-row"><span class="detail-label">Work Center</span><span class="detail-value">${escapeHtml(order.work_center)}</span></div>
                <div class="detail-row"><span class="detail-label">Shift</span><span class="detail-value">${order.shift}</span></div>
                <div class="detail-row"><span class="detail-label">Start</span><span class="detail-value">${order.start}</span></div>
                <div class="detail-row"><span class="detail-label">End</span><span class="detail-value">${order.end}</span></div>
                <div class="detail-row"><span class="detail-label">WIP Code</span><span class="detail-value">${escapeHtml(order.wip_code)}</span></div>
                <div class="detail-row"><span class="detail-label">Product Type</span><span class="detail-value">${order.product_type}</span></div>
                <div class="detail-row"><span class="detail-label">MSU Demand</span><span class="detail-value">${order.msu_demand}</span></div>
                <div class="detail-row"><span class="detail-label">Planned Qty</span><span class="detail-value">${order.planned_quantity} ${order.uom}</span></div>
            </div>
            <div class="detail-section">
                <div class="detail-section-title">Batch Assignment</div>
                <div class="detail-row"><span class="detail-label">Batch ID</span><span class="detail-value">${escapeHtml(order.batch_id)}</span></div>
                <div class="detail-row"><span class="detail-label">System</span><span class="detail-value">${order.assigned_system}</span></div>
                <div class="detail-row"><span class="detail-label">Batch Count</span><span class="detail-value">${order.batch_count}</span></div>
                ${target ? `<div class="detail-row"><span class="detail-label">Target MOQ</span><span class="detail-value">${target}</span></div>` : ''}
                ${tVal > 0 ? `
                <div class="detail-row"><span class="detail-label">Load Rate</span><span class="detail-value">${ratio.toFixed(1)}%</span></div>
                <div class="progress-bar"><div class="progress-fill ${barColor}" style="width:${Math.min(ratio, 100)}%"></div></div>
                ` : ''}
                ${order.batch_note ? `<div class="detail-row"><span class="detail-label">Note</span><span class="detail-value" style="white-space:normal;text-align:right;max-width:220px">${escapeHtml(order.batch_note)}</span></div>` : ''}
            </div>
            ${order.alerts && order.alerts.length ? `
            <div class="detail-section">
                <div class="detail-section-title">\u26A0 Alerts</div>
                ${order.alerts.map(a => `<div class="alert-item warning" style="margin-bottom:4px"><span class="alert-text">${escapeHtml(a)}</span></div>`).join('')}
            </div>` : ''}
            <div class="detail-section">
                <div class="detail-section-title">Decision Explain</div>
                <div class="decision-explain-box">${escapeHtml(order.decision_explain || 'N/A')}</div>
            </div>
        `;
        DetailPanel.open(html);
    },

    renderPagination(total) {
        const container = document.getElementById('orders-pagination');
        if (!container) return;
        const totalPages = Math.ceil(total / this.pageSize) || 1;

        let html = `<span class="pagination-info">${total} records</span><div class="pagination-buttons">`;
        html += `<button class="page-btn" ${this.page <= 1 ? 'disabled' : ''} data-page="${this.page - 1}">\u25C0</button>`;

        const maxButtons = 5;
        let startPage = Math.max(1, this.page - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) startPage = Math.max(1, endPage - maxButtons + 1);

        for (let p = startPage; p <= endPage; p++) {
            html += `<button class="page-btn ${p === this.page ? 'active' : ''}" data-page="${p}">${p}</button>`;
        }
        html += `<button class="page-btn" ${this.page >= totalPages ? 'disabled' : ''} data-page="${this.page + 1}">\u25B6</button>`;
        html += `</div>`;

        container.innerHTML = html;
        container.querySelectorAll('.page-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const p = parseInt(btn.dataset.page);
                if (p >= 1 && p <= totalPages) { this.page = p; this.render(); }
            });
        });
    },

    exportToExcel() {
        // Export filtered data (or all if no filter active)
        const data = this.filtered.length ? this.filtered : this.allOrders;
        if (!data.length) return;

        const headers = ['Order#', 'Material', 'Description', 'Work Center', 'Shift', 'Date',
                         'MSU Demand', 'System', 'Batch ID', 'Batch Count', 'WIP Code',
                         'Product Type', 'Planned Qty', 'UOM', 'Start', 'End', 'Alerts'];

        const rows = data.map(o => [
            o.order_number,
            o.material,
            o.material_description,
            o.work_center,
            o.shift,
            o.production_date,
            o.msu_demand,
            o.assigned_system,
            o.batch_id,
            o.batch_count,
            o.wip_code,
            o.product_type,
            o.planned_quantity,
            o.uom,
            o.start,
            o.end,
            (o.alerts || []).join('; ')
        ]);

        // Build CSV with BOM for Excel compatibility
        const BOM = '\uFEFF';
        const csvContent = BOM + [headers, ...rows].map(row =>
            row.map(cell => {
                const str = String(cell == null ? '' : cell);
                // Escape quotes and wrap in quotes if contains comma/quote/newline
                if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes(';')) {
                    return '"' + str.replace(/"/g, '""') + '"';
                }
                return str;
            }).join(',')
        ).join('\r\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        link.href = url;
        link.download = `HP_Orders_Export_${dateStr}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }
};

// ============================================================
// Alerts View
// ============================================================

const AlertsView = {
    allAlerts: [],
    activeFilter: 'all',

    async init() {
        try {
            const resp = await fetch('/api/alerts');
            this.allAlerts = await resp.json();
        } catch { this.allAlerts = []; }
        this.bindEvents();
        this.render();
    },

    bindEvents() {
        document.querySelectorAll('.alert-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.alert-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.activeFilter = btn.dataset.alertFilter;
                this.render();
            });
        });
    },

    render() {
        const container = document.getElementById('alerts-container');
        if (!container) return;

        let alerts = this.allAlerts;
        if (this.activeFilter !== 'all') {
            alerts = alerts.filter(a => a.severity === this.activeFilter);
        }

        if (alerts.length === 0) {
            container.innerHTML = `<div class="empty-state">
                <div class="empty-state-icon">\u2705</div>
                <div class="empty-state-text">No alerts</div>
                <div class="empty-state-hint">All systems nominal</div>
            </div>`;
            return;
        }

        const iconMap = { critical: '\u{1F534}', warning: '\u{1F7E1}', info: '\u2139\uFE0F' };

        container.innerHTML = alerts.map((a, i) => `
            <div class="alert-item ${a.severity} animate-in" style="animation-delay:${i * 30}ms">
                <span class="alert-icon">${iconMap[a.severity] || '\u2139\uFE0F'}</span>
                <div>
                    <div class="alert-text">${escapeHtml(a.text)}</div>
                    <a href="/orders" class="alert-link">View orders \u2192</a>
                </div>
            </div>
        `).join('');
    }
};

// ============================================================
// Summary View (with Charts)
// ============================================================

const SummaryView = {
    async init() {
        this.bindTabs();
        await this.loadAll();
    },

    bindTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                const panel = document.getElementById(`tab-${target}`);
                if (panel) panel.classList.add('active');
            });
        });
    },

    async loadAll() {
        await Promise.all([
            this.loadCharts(),
            this.loadSystemByDay(),
            this.loadLineByDay(),
            this.loadSegmentByDay(),
        ]);
    },

    async loadCharts() {
        await Promise.all([
            this.renderDailyTrendChart(),
            this.renderSystemDailyChart(),
        ]);
    },

    async renderDailyTrendChart() {
        const dom = document.getElementById('chart-daily-trend');
        if (!dom) return;
        try {
            const resp = await fetch('/api/summary/daily_trend');
            const data = await resp.json();
            if (!data.length) return;

            // Fetch heatmap to calculate daily target (total limit)
            let dailyTarget = 60; // default fallback
            try {
                const hmResp = await fetch('/api/heatmap');
                const hmData = await hmResp.json();
                if (hmData.length) {
                    const firstDate = hmData[0].date;
                    const firstDayItems = hmData.filter(d => d.date === firstDate);
                    dailyTarget = firstDayItems.reduce((sum, d) => sum + d.limit, 0);
                }
            } catch(e) {}

            const chart = echarts.init(dom);
            const dates = data.map(d => formatDateLabel(d.date));
            const categories = ['Shampoo', 'Conditioner', 'Other'];
            const colorMap = { Shampoo: '#6366f1', Conditioner: '#10b981', Other: '#71717a' };

            const activeCats = categories.filter(cat =>
                data.some(d => d[cat] && d[cat] > 0)
            );
            const lastCat = activeCats[activeCats.length - 1];

            const series = activeCats.map(cat => ({
                name: cat,
                type: 'bar',
                stack: 'total',
                barWidth: '50%',
                data: data.map(d => d[cat] || 0),
                itemStyle: {
                    color: colorMap[cat],
                    borderRadius: cat === lastCat ? [3, 3, 0, 0] : 0,
                },
                label: {
                    show: true,
                    position: 'inside',
                    formatter: params => {
                        const val = params.value;
                        return val > 0 ? val.toFixed(0) : '';
                    },
                    color: '#fff',
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: CHART_THEME.fontMono,
                },
                emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.3)' } },
            }));

            // Add invisible series for total label on top of stack
            series.push({
                name: 'Stack Total',
                type: 'bar',
                stack: 'total',
                barWidth: '50%',
                data: data.map(() => 0),
                itemStyle: { color: 'transparent' },
                label: {
                    show: true,
                    position: 'top',
                    formatter: params => {
                        const idx = params.dataIndex;
                        const total = activeCats.reduce((s, c) => s + (data[idx][c] || 0), 0);
                        return total.toFixed(0);
                    },
                    color: getChartTheme().labelColor,
                    fontSize: 12,
                    fontWeight: 600,
                    fontFamily: CHART_THEME.fontMono,
                },
                emphasis: { disabled: true },
                tooltip: { show: false },
            });

            // Add target reference line
            series.push({
                name: 'Target',
                type: 'line',
                data: dates.map(() => dailyTarget),
                lineStyle: { type: 'dashed', color: '#ef4444', width: 2, opacity: 0.7 },
                symbol: 'none',
                label: { show: false },
                emphasis: { lineStyle: { width: 2 } },
                tooltip: { show: true },
            });

            chart.setOption({
                tooltip: {
                    trigger: 'axis',
                    backgroundColor: '#18181b',
                    borderColor: 'rgba(255,255,255,0.08)',
                    textStyle: { color: '#fafafa', fontSize: 12, fontFamily: CHART_THEME.fontBody },
                },
                legend: {
                    bottom: 0,
                    data: activeCats.concat(['Target']),
                    textStyle: { color: CHART_THEME.textColor, fontSize: 11 },
                    itemWidth: 10, itemHeight: 10, itemGap: 16,
                },
                grid: chartBaseGrid({ bottom: 50, top: 40 }),
                xAxis: { type: 'category', data: dates, ...chartAxisStyle() },
                yAxis: {
                    type: 'value',
                    name: 'Batch Count',
                    nameTextStyle: { color: CHART_THEME.textColorDim, fontSize: 10 },
                    max: 70,
                    ...chartAxisStyle(),
                },
                series,
            });
            window.addEventListener('resize', () => chart.resize());
        } catch (e) { console.error('Daily trend chart error:', e); }
    },

    async renderSystemDailyChart() {
        const dom = document.getElementById('chart-system-daily');
        if (!dom) return;
        try {
            const resp = await fetch('/api/summary/system_daily');
            const data = await resp.json();
            if (!data.length) return;

            const chart = echarts.init(dom);
            const dates = [...new Set(data.map(d => d.date))].sort();
            const systems = [...new Set(data.map(d => d.system))];
            const dateLabels = dates.map(formatDateLabel);

            const series = systems.map((sys, idx) => ({
                name: sys,
                type: 'bar',
                data: dates.map(date => {
                    const item = data.find(d => d.date === date && d.system === sys);
                    return item ? Math.round(item.ratio * 100) : 0;
                }),
                itemStyle: {
                    color: CHART_THEME.colors[idx % CHART_THEME.colors.length],
                    borderRadius: [3, 3, 0, 0],
                },
                barGap: '10%',
                label: {
                    show: true,
                    position: 'top',
                    formatter: '{c}%',
                    color: '#a1a1aa',
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: CHART_THEME.fontMono,
                },
            }));

            chart.setOption({
                tooltip: {
                    trigger: 'axis',
                    backgroundColor: '#18181b',
                    borderColor: 'rgba(255,255,255,0.08)',
                    textStyle: { color: '#fafafa', fontSize: 12 },
                    formatter: params => {
                        let html = `<b>${params[0].axisValue}</b><br/>`;
                        params.forEach(p => {
                            html += `${p.marker} ${p.seriesName}: <b>${p.value}%</b><br/>`;
                        });
                        return html;
                    }
                },
                legend: {
                    bottom: 0,
                    textStyle: { color: CHART_THEME.textColor, fontSize: 11 },
                    itemWidth: 10, itemHeight: 10, itemGap: 12,
                },
                grid: chartBaseGrid({ bottom: 50, top: 40 }),
                xAxis: { type: 'category', data: dateLabels, ...chartAxisStyle() },
                yAxis: {
                    type: 'value',
                    name: 'Utilization %',
                    nameTextStyle: { color: CHART_THEME.textColorDim, fontSize: 10 },
                    max: 100,
                    axisLabel: { formatter: '{value}%', color: CHART_THEME.textColor, fontSize: 11 },
                    ...chartAxisStyle(),
                    splitLine: { lineStyle: { color: CHART_THEME.splitLineColor } },
                },
                series,
            });

            window.addEventListener('resize', () => chart.resize());
        } catch (e) { console.error('System daily chart error:', e); }
    },

    async loadSystemByDay() {
        try {
            const resp = await fetch('/api/summary/system_by_day');
            const data = await resp.json();
            this.renderTable('summary-system-table', data);
        } catch (e) { console.error(e); }
    },

    async loadLineByDay() {
        try {
            const resp = await fetch('/api/summary/line_by_day');
            const groups = await resp.json();
            const container = document.getElementById('summary-line-content');
            if (!container) return;
            let html = '';
            groups.forEach(group => {
                html += `<h3 style="font-family:var(--font-heading);font-size:13px;margin:16px 0 8px;color:var(--foreground-muted);font-weight:500">${escapeHtml(group.title)}</h3>`;
                html += this.buildTableHtml(group.data);
            });
            container.innerHTML = html || '<div class="empty-state"><div class="empty-state-text">No data</div></div>';
        } catch (e) { console.error(e); }
    },

    async loadSegmentByDay() {
        try {
            const resp = await fetch('/api/summary/segment_by_day');
            const data = await resp.json();
            this.renderTable('summary-segment-table', data);
        } catch (e) { console.error(e); }
    },

    renderTable(containerId, data) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = this.buildTableHtml(data);
    },

    buildTableHtml(data) {
        if (!data || !data.length) return '<div class="empty-state"><div class="empty-state-text">No data</div></div>';
        const cols = Object.keys(data[0]);
        let html = '<div class="table-wrapper"><table class="data-table summary-data-table"><thead><tr>';
        cols.forEach(c => { html += `<th>${escapeHtml(String(c))}</th>`; });
        html += '</tr></thead><tbody>';
        data.forEach(row => {
            const isTotal = String(row[cols[0]] || '').includes('Total');
            html += `<tr style="${isTotal ? 'font-weight:600;background:rgba(99,102,241,0.04)' : ''}">`;
            cols.forEach((c, ci) => {
                let val = row[c];
                if (val === null || val === undefined) val = '';
                else if (typeof val === 'number') val = Number.isInteger(val) ? val : val.toFixed(1);
                // Color code numeric cells based on value
                let cellStyle = 'text-align:center;';
                if (typeof row[c] === 'number' && ci > 0 && row[c] > 0) {
                    const intensity = Math.min(row[c] / 10, 1);
                    cellStyle += `background:rgba(99,102,241,${intensity * 0.08})`;
                }
                if (ci === 0) cellStyle = 'text-align:left;';
                html += `<td class="${typeof row[c] === 'number' ? 'col-mono' : ''}" style="${cellStyle}">${val}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        return html;
    }
};

// ============================================================
// Dashboard Charts (ECharts)
// ============================================================

const DashboardCharts = {
    async init() {
        await Promise.all([
            this.renderHeatmap(),
            this.renderDonut(),
        ]);
    },

    async renderHeatmap() {
        const dom = document.getElementById('chart-heatmap');
        if (!dom) return;
        try {
            const resp = await fetch('/api/heatmap');
            const data = await resp.json();

            // Dynamically adjust height based on number of systems
            const systems = [...new Set(data.map(d => d.system))];
            // Reverse so Total is at bottom (ECharts y-axis renders bottom-up)
            systems.reverse();
            const minHeight = Math.max(360, systems.length * 70 + 100);
            dom.style.height = minHeight + 'px';
            const chart = echarts.init(dom);
            const dates = [...new Set(data.map(d => d.date))].sort();
            const dateLabels = dates.map(formatDateLabel);

            const heatData = [];
            data.forEach(d => {
                const x = dates.indexOf(d.date);
                const y = systems.indexOf(d.system);
                heatData.push({
                    value: [x, y, d.ratio],
                    used: d.used,
                    limit: d.limit,
                    shifts: d.shifts,
                });
            });

            const t = getChartTheme();
            chart.setOption({
                tooltip: {
                    backgroundColor: t.tooltipBg,
                    borderColor: t.tooltipBorder,
                    textStyle: { color: t.tooltipText, fontSize: 12, fontFamily: t.fontBody },
                    formatter: p => {
                        const d = p.data;
                        let html = `<b style="color:${t.accentLight};font-size:13px">${systems[d.value[1]]}</b> \u2014 ${dateLabels[d.value[0]]}<br/>`;
                        html += `Utilization: <b>${(d.value[2] * 100).toFixed(0)}%</b> (${d.used}/${d.limit})<br/>`;
                        html += `<div style="border-top:1px solid ${t.borderColor};margin:4px 0;padding-top:4px">`;
                        d.shifts.forEach(s => {
                            const ratio = s.limit ? Math.round(s.used / s.limit * 100) : 0;
                            const color = ratio > 100 ? t.destructive : ratio > 75 ? t.warning : t.success;
                            html += `<span style="color:${color}">\u25CF</span> ${s.shift}: ${s.used}/${s.limit}<br/>`;
                        });
                        html += '</div>';
                        return html;
                    }
                },
                grid: { left: 120, right: 20, top: 40, bottom: 50 },
                xAxis: {
                    type: 'category',
                    data: dateLabels,
                    position: 'top',
                    axisLine: { lineStyle: { color: t.axisLineColor } },
                    axisLabel: { color: t.textColor, fontSize: 12, fontFamily: t.fontMono, margin: 8 },
                    splitLine: { show: false },
                    axisTick: { show: false },
                },
                yAxis: {
                    type: 'category',
                    data: systems,
                    axisLine: { lineStyle: { color: t.axisLineColor } },
                    axisLabel: {
                        color: t.textColor,
                        fontSize: 12,
                        formatter: val => val === 'Total' ? '{bold|' + val + '}' : val,
                        rich: {
                            bold: { fontSize: 13, fontWeight: 700, color: t.labelColor }
                        }
                    },
                    splitLine: { show: false },
                    axisTick: { show: false },
                },
                visualMap: {
                    min: 0,
                    max: 1.5,
                    calculable: false,
                    orient: 'horizontal',
                    left: 'center',
                    bottom: 4,
                    inRange: {
                        color: ['#e8eaf6', '#90caf9', '#66bb6a', '#fdd835', '#ef5350']
                    },
                    text: ['Overloaded', 'Free'],
                    textStyle: { color: t.textColorDim, fontSize: 12 },
                    itemWidth: 14,
                    itemHeight: 120,
                },
                series: [{
                    type: 'heatmap',
                    data: heatData,
                    label: {
                        show: true,
                        formatter: p => {
                            const sysName = systems[p.data.value[1]];
                            if (sysName === 'Total') {
                                return `{bold|${p.data.used}/${p.data.limit}}`;
                            }
                            return `${p.data.used}/${p.data.limit}`;
                        },
                        rich: {
                            bold: { fontSize: 13, fontWeight: 700, fontFamily: t.fontMono, color: '#1a1a2e' }
                        },
                        color: '#1a1a2e',
                        fontSize: 12,
                        fontFamily: t.fontMono,
                        fontWeight: 500,
                    },
                    itemStyle: {
                        borderColor: t.cardBg,
                        borderWidth: 2,
                        borderRadius: 4,
                    },
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 12,
                            shadowColor: 'rgba(99, 102, 241, 0.4)',
                            borderColor: t.accent,
                        }
                    }
                }]
            });

            window.addEventListener('resize', () => chart.resize());
        } catch (e) { console.error('Heatmap error:', e); }
    },

    async renderDonut() {
        const dom = document.getElementById('chart-donut');
        if (!dom) return;
        try {
            const resp = await fetch('/api/product_distribution');
            const data = await resp.json();

            const chart = echarts.init(dom);
            const colorMap = { 'Shampoo': '#6366f1', 'Conditioner': '#10b981', 'Other': '#71717a' };
            const seriesData = Object.entries(data).map(([name, value]) => ({
                name, value, itemStyle: { color: colorMap[name] || '#71717a' }
            }));

            const t = getChartTheme();
            chart.setOption({
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)',
                    backgroundColor: t.tooltipBg,
                    borderColor: t.tooltipBorder,
                    textStyle: { color: t.tooltipText, fontSize: 12 },
                },
                legend: {
                    bottom: 8,
                    textStyle: { color: t.textColor, fontSize: 11 },
                    itemWidth: 10, itemHeight: 10, itemGap: 16,
                },
                series: [{
                    type: 'pie',
                    radius: ['45%', '72%'],
                    center: ['50%', '44%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 5,
                        borderColor: t.cardBg,
                        borderWidth: 3,
                    },
                    label: {
                        show: true,
                        position: 'center',
                        formatter: () => {
                            const total = seriesData.reduce((s, d) => s + d.value, 0);
                            return `{big|${total}}\n{small|Orders}`;
                        },
                        rich: {
                            big: { fontSize: 28, fontWeight: 600, fontFamily: t.fontMono, color: t.labelColor, lineHeight: 36 },
                            small: { fontSize: 12, color: t.textColorDim, lineHeight: 20 }
                        }
                    },
                    emphasis: {
                        label: { show: true, fontSize: 15, fontWeight: 'bold' },
                        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' }
                    },
                    data: seriesData
                }]
            });

            window.addEventListener('resize', () => chart.resize());
        } catch (e) { console.error('Donut error:', e); }
    }
};

// ============================================================
// Init on page load
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    DetailPanel.init();
});
