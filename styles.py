# Styling & Color Palette for Antigravity Task Overlay (Dark Glassmorphism)

DARK_THEME_QSS = """
QWidget#MainWidget {
    background-color: rgba(18, 20, 26, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
}

QWidget#MainWidget.collapsed {
    border-radius: 20px;
}

/* Header & Pill Elements */
QLabel#TitleLabel {
    color: #f8fafc;
    font-size: 12px;
    font-weight: 700;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

QLabel#ModelBadge {
    color: #38bdf8;
    background-color: rgba(56, 189, 248, 0.12);
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 9px;
    font-weight: 600;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QLabel#TaskLabel {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 500;
    font-family: 'Segoe UI', 'Consolas', monospace;
}

QLabel#DurationLabel {
    color: #cbd5e1;
    font-size: 10px;
    font-weight: 600;
    font-family: 'Segoe UI', system-ui, sans-serif;
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 3px 8px;
    border-radius: 10px;
}

/* Status Indicator Dot */
QLabel#StatusDot {
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}

QLabel#StatusDot.running {
    background-color: #10b981;
    border: 2px solid rgba(16, 185, 129, 0.4);
}

QLabel#StatusDot.waiting {
    background-color: #f59e0b;
    border: 2px solid rgba(245, 158, 11, 0.45);
}

QLabel#StatusDot.idle {
    background-color: #64748b;
    border: 2px solid rgba(100, 116, 139, 0.3);
}

/* Action Buttons with SVG Icons */
QPushButton#IconBtn {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 13px;
    min-width: 26px;
    min-height: 26px;
    max-width: 26px;
    max-height: 26px;
    padding: 4px;
}

QPushButton#IconBtn:hover {
    background-color: rgba(255, 255, 255, 0.1);
}

QPushButton#IconBtn:pressed {
    background-color: rgba(255, 255, 255, 0.18);
}

QPushButton#CloseBtn:hover {
    background-color: rgba(239, 68, 68, 0.25);
}

/* Expanded Card Content */
QFrame#Divider {
    background-color: rgba(255, 255, 255, 0.08);
    max-height: 1px;
    border: none;
}

QWidget#BgProcessWidget, QWidget#CmdResponseWidget {
    background-color: transparent;
}

QLabel#BgProcessLabel {
    color: #c084fc;
    font-size: 11px;
    font-weight: 500;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QPushButton#BgCloseBtn, QPushButton#CmdCloseBtn {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 1px;
    color: #94a3b8;
}

QPushButton#BgCloseBtn:hover, QPushButton#CmdCloseBtn:hover {
    background-color: rgba(255, 255, 255, 0.15);
    color: #f1f5f9;
}

QComboBox#SessionSelector {
    background-color: rgba(255, 255, 255, 0.05);
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QComboBox#SessionSelector:hover {
    background-color: rgba(255, 255, 255, 0.09);
    border-color: rgba(56, 189, 248, 0.3);
}

QComboBox#SessionSelector::drop-down {
    border: none;
    width: 20px;
}

QComboBox#SessionSelector QAbstractItemView {
    background-color: #161822;
    color: #f1f5f9;
    selection-background-color: #2563eb;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    padding: 4px;
}

QLabel#SessionTagLabel {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QLabel#TaskCountBadge {
    background-color: rgba(56, 189, 248, 0.08);
    color: #38bdf8;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 6px;
    border: 1px solid rgba(56, 189, 248, 0.2);
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QLabel#SummaryHeader {
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 600;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QLabel#SubSummaryHeader {
    color: #94a3b8;
    font-size: 11.5px;
    font-weight: 600;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

/* Scroll Area for Logs */
QScrollArea#LogScrollArea {
    background-color: transparent;
    border: none;
}

QWidget#LogScrollContent {
    background-color: transparent;
}

QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 6px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.18);
    min-height: 20px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.32);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Log Item Row */
QFrame#LogItem {
    background-color: transparent;
    border-radius: 6px;
    padding: 2px 6px;
}

QFrame#LogItem:hover {
    background-color: rgba(255, 255, 255, 0.06);
}

QLabel#LogCategoryIcon {
    min-width: 16px;
    max-width: 16px;
}

QLabel#LogItemText {
    color: #e2e8f0;
    font-size: 11px;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

QLabel#LogItemText:hover {
    color: #ffffff;
}
"""
